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
merged blobs into individual cards -- the "split multi-print photos"
next step in `CLAUDE.md`) so each
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

Attempted the "split multi-print photos" next step -- carve a merged
multi-print blob into one crop
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

## Pass 1 caches measurements, so an unchanged file isn't remeasured (2026-08-16)

Reported directly: replacing one input and deleting its output still printed
"measuring 66 images" and took over a minute. The skip logic (§ Running in
CLAUDE.md) only ever covered pass 2 -- the expensive crop/colour rewrite --
because pass 1 exists to build the *folder-wide* desk target, which every file
including unchanged ones was re-measured to feed.

Fixed by writing each file's measurement (white_before, black_before, gain,
desk) to a new `desk` column in `report.csv`, and reading it back on the next
run for any file whose output already exists: `_cached_measurement()` parses
the row, and a file only takes the cheap path if all four fields (plus the
`desk` column itself, to tell "no desk" apart from "written before this
existed") parse cleanly -- any corruption or missing column falls back to a
fresh measurement for just that file, never a crash.

Verified on `chekis/main/` (66 files): first run after the change re-measured
all 66 once (backfilling `desk`, the column didn't exist yet) in ~85s; the very
next run, nothing changed, printed "measuring 0 of 66 images (66 unchanged,
reusing prior measurements)" and finished in 0.4s, with an *identical* desk
target ([65.6, 42.3, 29.7] both times). Deleting one output reproduced the
original complaint exactly, now fixed: "measuring 1 of 66 images (65 unchanged,
...)" in ~4.5s. `--force` and `--dry-run` both still behave as before --
`--force` ignores the cache entirely, `--dry-run` benefits from it but still
writes nothing. A duplicate output (present in both `balanced/` and `review/`,
the existing "something went wrong" signal) still forces a fresh remeasure, not
just a fresh reprocess, since it isn't eligible for the cache either.

## checleaner.html catches up on multi-print handling (2026-08-16)

Ported the multi-print-related work from this session's Python changes to the
phone app: `CROP_ASPECTS` best-fit cropping, the photo-window backstop
(`countWindows()`), and the paper-recentre fix -- plus `solidity`, an earlier
addition that had never made it into the HTML at all.

Porting `solidity` first paid for itself: it exposed a live bug. Without it,
`detectPrint()`'s single-card gate was just aspect+fill, so a flush 2x2 grid
(`PXL_20260131_165923174`, four cards laid edge to edge with no gaps) passed
outright and would have been warped into one mangled card. Solidity there is
`closedArea / hullArea`, where `closedArea` reuses `countWindows()`'s own
hole-filling (the JS port has no `cv2.findContours(RETR_EXTERNAL)` to hand it
a ready-made outer-contour area, so it derives the same quantity by filling
the paper mask's enclosed holes back in). First attempt used raw pixel count
instead of the filled area, and measured ~0.4-0.76 for every real single card
in the library -- because a card's photo *window* is a hole in the paper mask,
not paper, so raw count always undercounts a real card too. Fixed once
`closedArea` was threaded through; the grid then measured 0.946, comfortably
under the 0.97 gate, while 23 of 25 known singles landed at 0.99-1.0.

Window counts needed their own calibration, not Python's copied over: JS's
canvas decode/downscale isn't pixel-identical to `cv2.resize(INTER_AREA)`
(tried `imageSmoothingQuality: "high"`; helped a little, didn't close the
gap), so the same real photos count noticeably fewer windows in JS. A sweep of
all 110 files in `chekis/main/` found JS's worst genuine single at 5 windows,
not Python's 6, so `MULTI_WINDOWS` is **6** here, calibrated the same way
Python calibrated its own 7 (one above the worst genuine single measured) but
against JS's own distribution.

Full-batch comparison against Python's `report.csv` classifications: 95/110
agreed. Of the 15 that didn't, 7 are net improvements (a near-miss Python
itself left for review, JS's window backstop correctly auto-aligns), 6 are
pre-existing JS/Python blob-detection divergence unrelated to this session's
changes (already present before this port, just newly visible from doing a
full comparison for the first time), and 1 is a real, narrow regression:
`PXL_20260327_154304657`, a genuine single card with bright marker writing
near its border, where JS's mask has a small real gap Python's doesn't,
dropping solidity to ~0.56 and demoting it to a flagged near-miss instead of
an auto-crop. Accepted rather than chased further -- the failure direction is
safe (a flag costs a look; a wrongly-accepted grid, the bug solidity fixes,
costs a mangled photo) -- and the file still gets a correct colour-balanced
whole image, just not the auto-crop.

## A new batch surfaces four distinct detection bugs (2026-08-16)

A fresh batch came with 16 reported problems. They turned out to be four
separate causes, each fixed independently:

**1. Desk glare counted as a second print.** Four flawless single cards
(053032673, 145749754, 145802658, 145817569 -- aspect 1.577-1.585, fill ≥ 0.99)
were routed down the multi-print path because a specular highlight on the desk
segments as its own bright, near-neutral blob and broke the `n_blobs == 1` test.
Glare is never rectangular: those second blobs measured fill 0.78-0.82. Only
blobs at `PRINT_FILL` (0.90) or better now count toward the total.

**2. `minAreaRect` can't represent a card shot at an angle.** 073304486 and
073350228 are clean singles that measured aspect 1.506 and 1.485 -- outside the
[1.53, 1.65] accept band -- because a keystoned card is a trapezoid and
`minAreaRect` circumscribes it. Worse, feeding that rect to `warp` as the crop
source leaves its perspective transform nothing to correct (it degenerates to
affine), so the keystone survived into the output and desk spilled in on the
near edge: the "not cropped to correct size" complaint. `_card_quad()` fits the
four real corners and both files then measure 1.600 and 1.604; residual desk on
the near edge went 25 → 0 and 36 → 0 px. Guarded so a merged pile can't be
promoted (convex, opposite sides within 3%, ≥ 97% of its own bounding rect --
piles score 0.52-0.90). A fitted card also earns a gentler solidity floor
(0.95): angled cards measured 0.957 and 0.962 against the square-on 0.97. The
relaxation is small on purpose -- an overlapping 2-print blob that *does* pass
the corner test measured 0.916 and must stay out. The near-miss band still reads
the old `minAreaRect` aspect, since switching it pulled correctly-classified
multi-print photos into review for nothing.

**3. Aligned crops cut cards off.** The margin recentre added earlier moved the
crop's centre but kept it blob-*sized*, so on a scattered pile it slid real
cards off the edge. `_paper_bbox()` now sets centre *and* size from the true
paper. Where it looks turned out to matter in both directions: scanning the
whole rotated frame pulls in distant bright patches and over-grows the crop
until alignment declines outright (141154707, 153603211 both declined), while
scanning only inside the blob can't recover a border the segmentation clipped --
031653214 lost the top row of a nine-print pile that way, its blob stopping
317 px short of the real paper. A `PAPER_HALO` of 20% around the blob satisfies
both.

**4. Prints jammed against the crop edge.** `CROP_MARGIN` (4%) adds breathing
room, applied after the aspect is chosen and only if the grown crop still fits.
Applying it before broke the choice: a frame-filling pile picked a worse-fitting
shape purely because the better one no longer fit with margin added (caught by
`test_align_crop_picks_best_fit_aspect`, which flipped 4:3 → 1:1).

Reclassification across the whole library was verified file by file at each
step: the glare fix moved exactly the four cards, and the corner fit moved
exactly the two, with nothing else changing.

## Glare in detect_all_prints, and reorienting off the raw frame (2026-08-16)

Follow-up after the batch above: three of the files I had written off as
"prints fill the frame, can't be centred" were nothing of the sort, and the
correction was worth having.

**115252553 declined because of desk glare, not geometry.** Its three prints sit
in the middle of plenty of desk; a bright reflection in the bottom-right corner
was segmenting as a second blob (aspect 2.60, fill 0.815), and since
`align_multi()` crops around the union of every blob `detect_all_prints()`
returns, the crop had to stretch to that corner and no aspect fitted. The
`PRINT_FILL` filter added earlier only guarded `detect_print()`'s blob *count*.
Applying plain rectangularity here first made things worse -- a scattered pile is
one blob at fill 0.844, barely above that glare's 0.815, so the filter ate the
prints and the fallback returned everything unchanged. Keeping a blob when it is
either >= 25% of the largest blob's area *or* card-shaped works: a real card is
always rectangular and a real pile is never small. 115252553 now aligns 3:4 with
even margins.

**155935560 does not run off the frame either -- I misread it twice.** Measured
against a bounding box the user drew round the prints, the blob overshoots left
by 30 px and *bottom by 66 px* while undershooting right by 32 px: the prints are
fully contained, and the overshoot is a bridged-on sheen. The bottom 66 px of
blob carried 7% coverage against the prints' 100%, so `_paper_bbox` now trims
edge rows/columns below `PAPER_EDGE_COV` (25% of peak) -- which fixes this file
and 118 px of 145119616's glare while moving every known-good file's box by at
most 3 px. The threshold can't go higher: at 35% it starts eating real prints on
a staggered pile.

That left it failing by 14 px of 4080 -- the crop's *size* fitted, it just sat
slightly over one edge, because the prints really do span 96% of the frame width
horizontally. `place()` now nudges such a crop back inside instead of declining.
The nudge needs its cap (`CROP_NUDGE`, 2% of half-size): uncapped, a crop far
wider than the pile "fits" once slid hard against one edge, which let a
badly-shaped aspect win the selection and dumped all the desk on one side (one
photo came out 298 px lopsided, and 012024586 went from a symmetric 4:3 to a
16:9 with 298 px on one side). Capped, declines across the library fell from 13
to 6 and every previously-good crop stayed within ~8 px of centred.

**184109322 turned the wrong way because the face model was reading the balanced
frame.** `content_rotation()` was being handed the colour-corrected image;
pushing the whites to 238.8 cost it detections, and this photo scored 2 faces at
1.81 on the raw frame against 1 at 0.64 corrected -- enough to pick 180 over the
correct 270. It now reads the uncorrected frame. Swept every multi-print photo in
the library: exactly 1 of 75 changes (this one), and all eight files with a known
correct orientation agree on both inputs.

**Still unfixed: glare merged into the print blob** (130131692, 142612680,
145119616). When the segmentation close bridges a print to an adjacent sheen they
become one blob, so no per-blob filter applies, and the crop inherits the sheen
as a band of desk on one side. The sheen is as bright as paper (sweeping the
threshold to `L > 0.85 x p99` barely moved the box) and on a smooth desk as
smooth as paper, so neither brightness nor local variance separates them.
Anchoring the crop on photo windows does fix these three, but on a twelve-print
pile only 2 of ~12 windows were detected -- bright print content merges its window
into the border -- which would have collapsed that crop to a fraction of the pile
and silently cut prints off. Not shipped: an extra band of desk is a far better
failure than a cut print.

## Frame tilt read off the photo windows (2026-08-16)

Letting more piles crop (above) exposed a latent weakness: 052545093 had been
declining, and once it cropped it came out askew. Its merged blob's minAreaRect
reads -2.13 degrees, but that rectangle describes the *pile's outline* -- a
staggered arrangement of eight level cards is itself a tilted shape -- and a
sheen bridged onto the blob tilts it further. All eight of that photo's windows
agreed on -0.27 degrees, i.e. level.

`_dominant_tilt()` now averages the photo windows' own angles when at least
`MIN_TILT_WINDOWS` (2) of them are rectangular enough to trust
(`WINDOW_RECT_MIN`, 0.75), falling back to the blob rectangles otherwise. A
window is a print's picture area, so its rectangle is the card's rectangle, and
it sits inside the card where neither the staggering nor the desk reaches.

052545093 now levels correctly. Declines across `chekis/main/` fell again, 6 to
3 (13 before this run of work). Every previously-good crop stayed put except two
that picked up a 42-62 px imbalance from the slightly different angle -- both
still contain every print with margin on all sides.

This is also the first piece of the window-detection work: `_window_tilts()`
extracts per-window rectangles, which is the geometry the remaining sheen
problems need.

## Sheen-in-blob fixed by boundary sharpness (2026-08-16)

The three files left carrying a band of desk (130131692, 142612680, 155935560)
all had the same cause: the segmentation's 43-px close welds an adjacent desk
sheen onto a print, so the blob -- and every crop drawn from it -- swells past
the cards.

The answer turned out to be **how each piece of paper ends**, not what it looks
like inside. A card has a crisp edge against the desk; a sheen fades into it.
Splitting the unclosed paper into pieces and scoring each piece's own boundary
by mean Scharr magnitude separates them cleanly: sheen 235-350, cards 594-1511,
with `CARD_EDGE_SHARP` = 450 in open space between. `_sheen_free_bbox()` returns
the blob's bounding box with the soft-edged pieces cut off; all three files now
crop tight to their prints with even margins.

Three details were needed to make it safe. Pieces have to be eroded apart and
then measured *grown back*, because an eroded piece's boundary sits in flat paper
and scores low whatever it is. Only a bounding box is used -- the rectangle is
still fitted to the closed blob trimmed to that box, since re-fitting to the
fragmented raw paper moves the quad even at ~0% trim (this showed up as two files
shifting for no reason). And if less than `SHEEN_KEEP_MIN` (40%) of the bounding
box survives, the answer is discarded: one photo kept a single 0.5%-area piece
and its crop collapsed to nothing.

Window detection improved along the way too. Reading windows off the *unclosed*
paper mask finds far more than reading holes out of the closed one (9 against 2
on a twelve-print pile, 9 against 5 on another), because the close exists
precisely to fill windows and only the largest survive it.

Six *interior* statistics were measured before landing on the boundary, and every
one of them overlaps -- recorded so nobody repeats them:

1. **Brightness** -- sheen is as bright as paper; sweeping to `L > 0.85 x p99`
   barely moved the bounding box.
2. **Local variance** -- on a smooth desk the sheen is as smooth as a border.
   Fixes 145119616, does nothing for 130131692.
3. **Edge-coverage trim** -- already shipped for thin fringes (7% coverage);
   these sheens run 41-64%, and raising the threshold to reach them trims 26 px
   of real prints off a staggered pile.
4. **Keep unclosed-paper components touching an enclosed window** -- fixed
   130131692 (x 827 -> 632) and 142612680 (792 -> 604), but trimmed 47%, 41%,
   33% and 20% off four files whose cards' windows went undetected, three of
   which then declined outright.
5. **Anchor on any dark region inside the blob** -- no regressions, no fixes: the
   sheen touches an inter-card gap and survives.
6. **Anchor on photo-shaped dark regions only** -- still trimmed 305 px and
   325 px off two good files.

The populations overlap on every statistic tried: keep-ratio 0.63-0.77 for the
correct trims against 0.31-0.84 for the wrong ones; dark fraction in the trimmed
strip 0.34-0.40 against 0.42-0.48; dropped-lobe area 3.4x the median window
against 4.8x. Two files also regressed at ~0% trim, which pinned a second
problem: refitting the rectangle to the *fragmented* unclosed mask moves the quad
even when nothing is removed, so any future version must trim the closed blob
rather than re-fit to raw paper.

They all fail for one reason: windows are found for only some cards, so "paper
not near a window" is not "not a card". The boundary test works precisely
because it never has to find every window.

Verified across the library: declines stay at 3 (the same three as before, all
frame-filling), no previously-good crop moved, and the twelve spot-checked
aligned files are unchanged. 18 tests pass.

## A cut print, two lopsided crops, and six uncropped piles (2026-08-17)

Four separate causes behind the next round of reports.

**A print was being cut in half (073507152).** Two faults compounded. The crop
extent was read off each blob's `minAreaRect` *corners*, but that rectangle is
itself rotated, so on a tilted pile its corner box bounds far more than the
prints -- here x[-17,3512] y[-475,3179] on a 3583x2698 frame. Detections now
carry the blob's `hull`, and the extent is measured from that. Then
`_paper_bbox`'s edge-coverage trim removed a further 656 px, because a tilted
card's leading corner ramps up as gently as a sheen fringe (1% rising to 5% over
164 columns) and the trim could not tell them apart. That trim is gone: sheen is
removed from the blob itself by boundary sharpness, which a tilted corner passes
however thin it is.

**Sheen trimming was cutting the wrong thing.** `_sheen_free_bbox` was keeping
what it could prove was card, which silently discarded every piece too small to
judge -- including that same tilted-corner wedge. It now subtracts what it can
prove is *sheen*, and pulls a side in only where the sheen sticks out past the
cards. Erasing the sheen's own pixels is not enough on its own, because the
close also filled the dark gap it was bridged across and that fill holds the box
out at full width by itself.

**A frame-filling pile declined rather than cropping (155935560).** Its best
shape missed by 136 px, so the target is now retried at 97% and 94%. What that
eats is leftover sheen. It stops at 94% on purpose: at 90% two other files
started cutting real prints, which is worse than not cropping.

**Six multi-print photos sat in review uncropped** (165923174, 142631910,
153435918, 154241942, 011948001, 012314592). All six are plainly several prints;
all six landed in the near-miss band, which left them whole. Nothing available
separates a badly-fitted single card from prints overlapped into a card-shaped
pile -- window counts overlap completely (these six: 0-9 raw windows, genuine
singles: 0-5), as do fill and solidity. So the *policy* changed rather than the
classifier: a near-miss is now levelled and cropped like any other multi-print
photo and keeps its flag. If the guess is ever wrong the result is a levelled
frame around one card rather than a mangled one, and review still gets it.

Across the library: worst margin asymmetry fell from 253 px to 112, declines
went 3 -> 4 (two frame-filling piles whose prints genuinely run off the frame),
and 84 balanced / 22 review. 19 tests pass.

## Crops stopped cutting rows: the nudge cap is the crop's own slack (2026-08-17)

Three photos came back with a whole row of prints missing (155935560,
154257343, 055435791). Two mechanisms were sliding the crop off the prints, both
introduced trying to rescue frame-filling piles from declining:

**Shrink-to-fit.** When nothing placed, the target was retried at 97% and 94% of
its size, on the theory that it would eat the leftover sheen. It cannot: the crop
has to *contain* the prints, so shrinking it below their own extent eats prints
and nothing else. All three cut rows trace to the 94% retry. Removed outright --
a photo left whole beats a photo with a row missing.

**An arbitrary nudge cap.** `place()` could slide the crop by up to 2% of its own
size to bring it inside the frame. That number has nothing to do with whether a
print leaves the crop, so it was wrong in both directions: too tight for photos
that could be placed perfectly safely (155935560's best shape needed a 214 px
shift into 301 px of spare margin), and able to slide *past* the prints when the
crop was pinned. The cap is now exactly the crop's own slack, `hw - bw2` per
axis: inside it a print can never leave the crop, outside it one always does. A
crop pinned tight on an axis now cannot move along it at all, plus the same
`pad` of leeway the frame test already allows, so a fractional tilt costing a
pixel or two at the corners doesn't sink an otherwise fine placement.
Candidates are also scored on how far they had to slide, so a centred shape beats
one that only works jammed against an edge.

All three now contain every print. Declines went 4 -> 5: the two extra
(061906898, 041152515) were previously "cropping" by cutting -- every candidate
for them needs a shift larger than its slack on the pinned axis, so their prints
genuinely cannot be framed once levelled, and leaving them whole is the correct
answer. 155935560 now carries an uneven bottom margin instead of a missing row,
which is the honest trade: its pile is 1.67:1 and neither 4:3 nor 16:9 fits it
well.

## A lopsided crop is worse than no crop (2026-08-17)

Reported directly, and it settles a question that had been driving several
rounds of tuning: "if one side seems to get zero margin then it's better to not
crop, since leaving space on one side with no space on the other looks worse
than having some space on both sides."

`align_multi` now rejects any candidate whose smaller margin is under
`CROP_BALANCE` (25%) of its larger one on either axis, and leaves the photo
whole if nothing balanced can be placed. Symmetric zero margins stay fine --
tight all round looks deliberate, and most cropping files sit at exactly 0/0 on
one axis. It is one bare edge *facing* a wide one that is barred.

Calibrating it against the library first mattered: a threshold of 0.15 left
155935560 in at 87 px against 503 (ratio 0.17), which is exactly the look being
complained about, while 0.25 catches it and still passes every well-balanced
file (the closest keeper, 012024586, sits at 0.33). Four photos now stay whole
for this reason -- 154257343 and 055435791 as reported, plus 155935560 and
073449276 -- taking declines from 5 to 8 and the worst margin asymmetry from
464 px to 140.

## 2026-08-17 — not every background is the desk

Prompted by a plain question: the walnut desk won't always be the background, so
what keeps the prints' colour consistent when it changes? Five photos were
already like that. Measuring all 140 files in the library found **two separate
mechanisms, only one of which was actually misbehaving.**

### The white anchor was fine — by luck, not design

`measure()` took white from the brightest smooth pixels of the *whole frame*.
That only finds the paper border because the walnut is darker than paper.
Confining the mask to the detector's blobs changed the result on **3 of 140**
files; on the other 137 the white was identical and the gain moved 0.000% at
both median and p90. So the anchor was never wrong on any fronts photo,
including all five that were asked about.

The three it does change are the backs batch — dark cards on a pale desk, where
the background wins outright:

| file | white from frame | from paper | gain error |
|---|---|---|---|
| `20260728_035448131` | 137, 161, 187 (blue) | 145, 140, 132 (neutral) | **116%** |
| `20260728_035633320` | 143, 171, 195 | 146, 154, 151 | 77% |
| `20260728_035651788` | 134, 163, 164 | 135, 163, 144 | 34% |

Shipped anyway, precisely *because* it is a no-op today: it costs the calibrated
library nothing and removes the dependence on background brightness before a
pale surface makes it a real problem. Black was left frame-wide — confining it
moves 8 files by 2–27%, since on this desk the darkest 0.5% is desk shadow and
the 2.2 calibration is built on that.

### Desk matching was the actual fault

The desk test is walnut-shaped (warm, mid-dark, smooth), and a pale surface still
passes it. Those files were being pinned at the gamma clamp — 1.16 on every
channel against 0.94–0.99 for a genuine desk photo — and since the gamma is
applied to the whole frame, the prints' midtones paid for it.

The fix reuses the clamp as the test rather than adding a threshold: if the
damped curve can't reach the target without being clipped, that background isn't
this batch's desk, so skip the match instead of applying the largest correction
allowed. On `chekis/main` that is exactly 6 of 105, with nothing else close:

| file | desk (sRGB) | vs batch median 44 | unclamped gamma |
|---|---|---|---|
| `20260211_053747452` | 200, 167, 132 | 3.8× | 1.16 on all 3 |
| `20260815_224341680` | 218, 142, 89 | 3.4× | 1.16 on all 3 |
| `20260815_222540256` | 205, 131, 81 | 3.2× | 1.16 on all 3 |
| `20260630_140740030` | 203, 77, 54 | 2.5× | 1.16 on all 3 |
| `20260803_034833604` | — | 1.9× | 1.16 on 1 |
| `20260526_055435791` | 124, 78, 36 | 1.8× | 1.16 on 2 |

Two of those are genuinely different surfaces (pale pine, a grey table), one is
held in the hand, and **three have no visible desk at all** — the prints fill the
frame, so what the mask read was skin and clothing leaking in. That last group
was not anticipated; the clamp caught it for free, which is the argument for the
clamp over a brightness ratio. A 2× median-luminance rule was implemented first
and rejected: it missed `055435791` and `034833604`, and the luminances form a
continuum (166, 150, 139, 111, 81, 79, 57, 56, …) with no cut that separates
them cleanly.

Target moved [60.9, 41.7, 29.6] → [60.6, 41.5, 29.3], i.e. barely — medians are
robust and the outliers were never the problem. The point is not correcting
those six.

Recorded as a new `report.csv` column, `desk_match`, and deliberately not as a
flag: skipping the match makes the output more faithful, so there is nothing to
review.

### Ported to the phone app

The white anchor half only — desk matching needs a folder-wide median and the
app sees one photo at a time. `detectPrint()` returns a `paper` mask and now
runs before the colour pass. Sweeping all 106 files through the page moved
white by at most one sRGB unit on 10 of them, gain by ~1%, and nothing else at
all — no kind, crop, size, window count or flag changed.

Two things fell out of doing it. Blob ids were being numbered `blobs.length + 1`
*before* the size test, so a rejected component handed its id to the next one
and `label` had duplicates — harmless for the existing readers, not harmless for
a mask keyed on it; ids are now one per component. And `tools/webdetect.py`
reported "0 of 106 changed" for a change that demonstrably moved the colour,
because it tracked only geometry. It now tracks `white` and `gain` too. That is
the second time that tool has been caught blind by a field it wasn't recording
(the first was output dimensions) — the lesson each time was to make the
deliberate change first and check the tool *notices*.

## 2026-08-17 — two singles the window backstop was refusing to crop

Reported from `rancheki/`: `033246201` and `033323480`, both plainly one cheki,
neither being cropped. Both pass the single test comfortably (aspect 1.609 /
1.595, fill 0.997, solidity 0.994 / 0.996) and both were being demoted by
`count_windows` returning exactly **7**, the `MULTI_WINDOWS` threshold.

The cause is high-key prints. The paper mask is *bright and near-neutral*, so a
pale picture — white blouse, bright sky, sun-bleached rock — segments as paper
and leaves scattered dark specks instead of one photo window. The count then
measures the print's exposure, not how many prints there are.

Swept `main/` + `rancheki/` for a threshold that separates. There isn't one:

| population | true singles | true multis |
|---|---|---|
| passes the confident single test | 44, up to **7** windows | 1, at **7** windows |
| near-miss only | **0** | 27 |

So the count is worthless exactly where it was doing damage, and free where it
isn't. Split into two thresholds: `--multi-windows` stays 7 for near-misses,
`--card-windows` is 8 for confident fits. What actually separates the one pile
(`main/20260811_012024586`, a 3-print row) from the 44 cards is aspect — cards
top out at 1.631, it sits at 1.642 — so `--aspect-hi` went 1.65 → 1.64.

Result: **0 files in `main/` reclassify**, and the two rancheki files crop as
singles. `012024586` still lands in `balanced/` as aligned, now via aspect
instead of the count.

`tools/detect.py` was reporting "single" for both files while a real run said
"aligned" — its `classify()` had never mirrored the window backstop, despite a
docstring promising it stayed in step. Now fixed and passed the real count.

### The third report: a crop about a degree askew

`rancheki/PXL_20260601_053951339` (a 3-print row, near-miss, in `review/`) is
levelled to −0.0° when its blob reads +1.204°. Two surviving "windows" of 2.6 k
and 10 k px both report −0.0°, because a rectangle that small snaps to
axis-aligned, and `MIN_TILT_WINDOWS` (2) lets them outvote the blob.

Five discriminators were measured and all rejected — see `docs/PIPELINE.md` § 6
for the numbers. Every one buys this degree back by costing tens of degrees on
staggered piles whose blob tilt is genuinely garbage (one falls back to −33°).
Left as it is: the file is already flagged for review.

### The phone app deliberately does not get this fix

Checked, and the answer is no. The same shape of bug is there — one shared
window threshold guarding both gates — and one of the two singles
(`033323480`, 7 windows) plus one other (`073350228`, 6) are demoted by it. But
the JS cannot afford the same split, because its solidity is an approximation
(`closedArea / hullArea`, no `findContours`) that cannot see the notches in a
staggered row. Of the four files passing the full JS single gate, the two
singles and the two multis interleave on every metric — windows 6/7 against
6/7, aspect 1.579/1.585 against 1.576/1.639 — so any raise that frees the
singles also frees `20260221_153435918`, three unevenly-laid prints that Python
rejects on shape (0.863/0.793) and the app reads as a clean card (0.995/0.998).

Left at 6. Two singles come out levelled instead of cropped, whole and
rotatable by hand; the alternative is a real row warped into one card. The
proper fix is a true external-contour area in the JS, not a moved threshold.

Getting to that answer needed numbers the page never showed: `runFile()` now
keeps the detection on `lastDetection`, and `tools/webdetect.py` records
`aspect`, `fill` and `solidity`. Without them a sweep can only see which side
of a threshold each file fell, never how far.

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
