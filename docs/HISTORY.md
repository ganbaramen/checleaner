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

`062001471` was added later: a two-print close-up with the cards running
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
Python only at the time; the port landed later the same day (see the "catches up on multi-print handling" entry).

Test file: `023437053` (two touching prints,
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
nothing to do with the border -- found on `022950306`, where the
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
`034511524` and `034606768`, the card fills nearly the
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
`012314592` is an 11-card grid, not a single print, but the merged
blob's overall aspect (1.626) and fill (0.944) both happened to land inside
the single-card acceptance window, so it got warped and cropped as if it
were one card -- the "crop" ended up keeping nearly the entire original
frame (quad spanned 82% of the width, 99.9% of the height). Tried "does the
blob touch the frame edge" as a discriminator first; rejected it after
finding a *known-good* single (`002138234`, a legitimate close-up
shot) with the same near-zero margin on every side -- edge-touching alone
isn't safe. The signal that actually works: solidity, raw contour area over
convex hull area. A real card's border has no internal seams, so its raw
contour already equals its hull (solidity 1.0000, confirmed on
`002138234`); the 11-card grid's seams between cells leave notches
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
| 023359428 | 1 row of 2 portrait | 90° |
| 015640226 | 1 row of 3 portrait | 90° |
| 015731072 | 1 row of 3 portrait | 90° |
| 023126095 | 1 row of 2 landscape + 1 row of 4 portrait | 90° |
| 023727013 | 1 row of 4 portrait | 180° |

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
(`165923174`, four cards laid edge to edge with no gaps) passed
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
`154304657`, a genuine single card with bright marker writing
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
| `035448131` | 137, 161, 187 (blue) | 145, 140, 132 (neutral) | **116%** |
| `035633320` | 143, 171, 195 | 146, 154, 151 | 77% |
| `035651788` | 134, 163, 164 | 135, 163, 144 | 34% |

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
| `053747452` | 200, 167, 132 | 3.8× | 1.16 on all 3 |
| `224341680` | 218, 142, 89 | 3.4× | 1.16 on all 3 |
| `222540256` | 205, 131, 81 | 3.2× | 1.16 on all 3 |
| `140740030` | 203, 77, 54 | 2.5× | 1.16 on all 3 |
| `034833604` | — | 1.9× | 1.16 on 1 |
| `055435791` | 124, 78, 36 | 1.8× | 1.16 on 2 |

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
(`main/012024586`, a 3-print row) from the 44 cards is aspect — cards
top out at 1.631, it sits at 1.642 — so `--aspect-hi` went 1.65 → 1.64.

Result: **0 files in `main/` reclassify**, and the two rancheki files crop as
singles. `012024586` still lands in `balanced/` as aligned, now via aspect
instead of the count.

`tools/detect.py` was reporting "single" for both files while a real run said
"aligned" — its `classify()` had never mirrored the window backstop, despite a
docstring promising it stayed in step. Now fixed and passed the real count.

### The third report: a crop about a degree askew

`rancheki/053951339` (a 3-print row, near-miss, in `review/`) is
levelled to −0.0° when its blob reads +1.204°. Two surviving "windows" of 2.6 k
and 10 k px both report −0.0°, because a rectangle that small snaps to
axis-aligned, and `MIN_TILT_WINDOWS` (2) lets them outvote the blob.

Five discriminators were measured and all rejected — see `docs/PIPELINE.md` § 6
for the numbers. Every one buys this degree back by costing tens of degrees on
staggered piles whose blob tilt is genuinely garbage (one falls back to −33°).
Left as it is: the file is already flagged for review.

**Superseded 2026-08-20.** The five rejections still stand, and so does the
reason: no filter *inside* the window path works. What was wrong here was the
conclusion that this was one file's problem. It is 81 of 140, and the fix was to
stop deciding tilt from windows at all — see the 2026-08-20 entry. This file now
levels at 1.10°.

### The phone app deliberately does not get this fix

Checked, and the answer is no. The same shape of bug is there — one shared
window threshold guarding both gates — and one of the two singles
(`033323480`, 7 windows) plus one other (`073350228`, 6) are demoted by it. But
the JS cannot afford the same split, because its solidity is an approximation
(`closedArea / hullArea`, no `findContours`) that cannot see the notches in a
staggered row. Of the four files passing the full JS single gate, the two
singles and the two multis interleave on every metric — windows 6/7 against
6/7, aspect 1.579/1.585 against 1.576/1.639 — so any raise that frees the
singles also frees `153435918`, three unevenly-laid prints that Python
rejects on shape (0.863/0.793) and the app reads as a clean card (0.995/0.998).

Left at 6. Two singles come out levelled instead of cropped, whole and
rotatable by hand; the alternative is a real row warped into one card. The
proper fix is a true external-contour area in the JS, not a moved threshold.

Getting to that answer needed numbers the page never showed: `runFile()` now
keeps the detection on `lastDetection`, and `tools/webdetect.py` records
`aspect`, `fill` and `solidity`. Without them a sweep can only see which side
of a threshold each file fell, never how far.

## 2026-08-20 — tilt taken off the prints' edges, and a rationed crop margin

Two complaints on the same two photos: `main/012024586` came out
with lopsided margins, and `main/154241942` came out askew. Both
sit on the multi-print alignment path, and they turned out to be separate bugs.

### The tilt was being decided by ink

`154241942` reported `align_tilt` −0.00 on a row visibly leaning 1.5°. Its blob
rectangle said −1.59, which was about right, so the wrong answer was coming from
the window path that overrules it. Dumping the holes explained why. Its three
real photo windows scored 0.617, 0.667 and 0.726 on rectangularity, all under
`WINDOW_RECT_MIN` (0.75) and all rejected — the signature crosses out of the
picture area into the border and merges with it, so the hole isn't a rectangle
any more. What survived were two loops of pen inside the border, 3.4 k and 4.0 k
px, which the morphology leaves perfectly square: two windows, both −0.00°,
`MIN_TILT_WINDOWS` satisfied, row reported level.

This is the same failure recorded as unfixable on 2026-08-17 for
`rancheki/053951339`. It is much more common than that entry
assumed: across 140 photos, **81** have their tilt decided by holes under a
quarter the size of the biggest one in the same blob. Most of those read −0.00,
which is why so much of the library looked level.

A relative area floor does isolate the loops, but it drops two files below
`MIN_TILT_WINDOWS` onto blob rectangles that are themselves wrong — the −33°
staggered pile the old entry warned about, and +13° on another. So the
measurement moved outside the window path entirely: `_edge_dirs()` now reads the
angle off the prints' **own outline**, every straight run of it weighted by
length squared, gated on how much those runs agree (`TILT_COHERENCE`, 0.95).
See `docs/PIPELINE.md` § 6.

Validated against an independent score — how well the paper mask fills its
axis-aligned bounding box after being rotated by the candidate angle — over all
140 photos:

| agreement | files | edge angle better | old path better |
|---|---|---|---|
| ≥ 0.95 | 67 | 47 (total +0.767) | 16 (total −0.022) |
| 0.90–0.95 | **0** | — | — |
| < 0.90 | 7 | 2 (+0.054) | 5 (−0.069) |

The empty band is why the gate is where it is. Above it the wins are large and
the losses are all fourth-decimal; below it that reverses, and those files are
cards keystoned steeply enough that their borders aren't two pairs of parallels
any more — a real measurement of something that isn't a rotation.

Biggest movers, all confirmed by rotating the source and looking:

| file | was | now |
|---|---|---|
| `073507152` | −0.00 | **−33.16** (two prints overlapping at a steep angle; genuinely that crooked) |
| `041152515` | 6.48 | 17.94 |
| `073338220` | 3.31 | 11.64 |
| `154241942` | −0.00 | −1.46 (the complaint) |
| `rancheki/053951339` | −0.00 | 1.10 (the 2026-08-17 "unfixable") |
| `153435918` | 0.69 | −0.11 |

Reprocessing `chekis/main/` (106 files) and `chekis/rancheki/` (22) with
`--force`: **no file changed `dest`, `kind`, `flags`, white or gain** except two.
`073507152` went `aligned` → `multi`: once it is turned 33° no crop shape fits
inside the frame, and align_multi declines rather than reach into the blank the
rotation opened. It is left whole and still colour-balanced, which is the
documented preference. In rancheki, `062001471` went the other way,
`multi` → `aligned`. Everything else that moved moved `align_tilt` only, 55 of
106 and 9 of 22, and no crop shape changed anywhere.

### The margin was being spent where there was no desk

`012024586` is a row of three lying 36 px from the left edge of its frame and
330 from the right. The 4:3 crop chosen for it sits dead centre on the prints at
its natural size — margins 0 and 0. `CROP_MARGIN` then grows it 4% on *both*
sides, which no longer fits, so `place()` slides it right against the left edge
and every new pixel of margin lands on the right: 36 px against 110.

`lopsided()` doesn't catch it (36/110 is inside `CROP_BALANCE`) and loosening it
far enough to would start refusing crops that are merely tight. Instead the
margin is now rationed in `CROP_MARGIN_STEPS` (4) steps, taking the largest part
that still places on the prints' own centre. This frame takes half of it and
comes out 36/36 horizontally, 250/250 vertically.

### Coverage

`tests/test_pipeline.py` is up to 28. New: a staggered pile whose blob rectangle
reads 32° off while every card in it is level; a signed row whose windows are
all ragged; a coherence check that scattered card angles score below the gate; a
one-sided-desk row whose crop must come out even; and a real-photo tier pinning
four tilts that used to read exactly 0.00. The margin test now checks both axes
and includes `012024586`. All five fail against the previous `checleaner.py`.

### The phone app gets the margin fix, not the tilt fix

`alignMulti()`'s grow step is rationed the same way. Sweeping `chekis/main/`
through the real page with `tools/webdetect.py --compare`: 18 of 106 change, all
of them **size only** — no verdict, crop shape, window count, white or gain
moves. Some grow rather than shrink, which is the same fix seen from the other
side: where the full 4% used to be refused outright the ladder now finds a
smaller part of it that fits centred. `012024586` comes out even in the app too. The edge-direction tilt is
not ported: it needs a contour tracer, which the app doesn't have — the same
gap that makes its solidity an approximation. `dominantTilt()` still averages
blob rectangles and can still be fooled by a staggered pile. Writing the tracer
closes both.

## 2026-08-22 — review cut from 22 files to 3, and a card rescued from its own glare

Looking through `main/review/`: 20 of the 22 files there were fine. The two that
weren't were `145119616` (a single card, badly cropped) and `154257343` (a
purikura sheet, not cropped at all).

### `145119616`: glare welded to the card

Its blob reads aspect 1.434, fill 0.858 — nowhere near a card — because a patch
of desk glare sits off its bottom-right corner and the 43-px segmentation close
welds the two together. `_sheen_free_bbox()` already finds the right box; it just
wasn't allowed to speak, because feeding the trimmed box into the single-vs-multi
decision turns a 3-print pile into a 1.88 slab (recorded 2026-08-16).

`single_fit()` now gives it one try, and only when the **aspect** is what failed.
That condition is the safety: an appendage distorts the fitted rectangle, while a
blob that was already card-shaped and failed on fill or solidity is *ragged*,
which is what a pile looks like from outside. Sweeping the library, the naive
version (retry on any failure) promotes two files — the card, and
`153435918`, the three-print row `docs/PIPELINE.md` § 3 explicitly warns must
never be cropped as one card, which would come out warped. The aspect condition
separates them: 1.434 against 1.581. With it, exactly one file moves.

Four other separators were measured first and all overlap:

| | `145119616` (card) | `153435918` (row) |
|---|---|---|
| photo windows | 1 | 6 (genuine singles reach 6 too) |
| windows lost to the trim | 0 | 0 |
| share of the cut that is really sheen | 38% | 34% |
| mean chroma per piece | 4.4 | 4.7 |

`145119616` now crops to 1800 × 2867 at aspect 1.576. The window backstop still
guards the rescue: it counts 1, far below `--card-windows` (8).

### `154257343`: not fixed, and here is how far it got

The purikura sheet has a large glare patch running off the top-left corner of the
frame, merged into the prints' blob. Every crop shape is then flush against two
frame edges, `lopsided()` rejects all of them, and `align_multi()` declines — so
the photo is left whole. It is genuinely the same bug as above, and none of the
levers reach it:

- `_sheen_free_bbox` scores that patch **548** mean Scharr, against card pieces
  at 590–929. `CARD_EDGE_SHARP` is 450 and there is no gap to move it into.
- The patch encloses no photo window, but neither do three real card pieces of
  `153435918` (windows 0, 0, 0 against the glare's 0).
- Its chroma is 4.69 against the cards' 4.44–5.56.

Left in `review/`, which is now the *only* thing in `main/review/` that is
actually wrong, and it is there for the right reason: a near-miss left whole.

### What goes to review at all

`review/` is for outputs likely to be wrong. Judged against the whole batch:

| check | fired on | actually wrong | now |
|---|---|---|---|
| `fit rejected` | 12 | 2 | narrowed to `left whole (fit rejected: …)` |
| `desk still on … edge` | 4 | 0 | a note (`REVIEW_NOTES`) |
| `white reference … clipped` | 6 | 0 | a note |

Notes are written to `report.csv` and printed, but do not move the file. Both
measure something real that is not a reason to hold a photo back:

- The residual-desk reading is **saturated, not graded**. `residual_desk()` looks
  only 2% into each edge on purpose — probe 10% instead and it starts reading the
  print's own picture area, reporting a "residual" on 25 of 32 crops. So the four
  photos that fired read 36 px and 57 px, which *are* that 2% on those axes.
  Raising `--max-residual` past them would disable the check rather than relax
  it, and each is a hairline along one edge.
- A clipped white reference has never broken the correction. The worst photo in
  the library blows **69%** of its bright pixels and still keeps 103,000 usable
  border pixels — 129× the 800 `measure()` treats as too few — and lands on white
  239.0. All six flagged photos landed within a point of target.

The near-miss band is narrowed rather than dropped, because it is the check that
caught both real problems. It now fires only when the frame was **left whole**:
levelled and cropped, a near-miss is a good multi-print result whether or not the
card guess was right (11 of them, every one fine), but left whole the pipeline
has applied no geometry at all. `kind` still records `single?` either way, and
`aspect`/`fill`/`solidity` now go into `report.csv` columns instead of living
only inside the flag text (`solidity` is a new column).

Result on `chekis/main/` (106 files): **103 balanced, 3 review**, from 84/22. The
three are all near-misses left whole. `chekis/rancheki/` goes from 1 to 0. No
file's colour changed; `145119616` is the only file whose geometry did.

### The overcrop that came out from under it

Cropping `145119616` for the first time exposed a second, older bug immediately:
the crop came back with the top of "2026.3.7" sliced off. The fit was right --
its top edge sits exactly on the card's -- and `trim_desk()` then pulled 53 px
further in.

`trim_desk` scans each edge inward for desk-coloured lines and takes the
**deepest hit anywhere** in its 3.5% window. Instrumenting the scan: rows 0-24
of the border read 0.000 desk, and rows 42-54 read 0.09-0.24. That is not desk
creeping in from the edge, it is the *writing* -- black marker is dark (`L < 1.25
x` the desk's) and picks up enough of the desk's warmth to clear the projection
test too. One deep row of ink set the deepest hit to the cap.

Real desk is contiguous with the edge it came in from; ink in the border is an
island with clean paper in front of it. The scan now ends a run after `TRIM_GAP`
(6) clean lines. Sweeping every photo that crops as a single, this changes the
insets on exactly one file -- the one complained about. Every trim any other
file needs was already contiguous with its edge, which is also why the old
behaviour survived this long. Gap values 4-10 all give that same answer; at 2,
`033323480`'s genuine 13-px right trim drops to 0.

### The phone app gets this one

`checleaner.html` had both bugs and now has both fixes — `detectPrint()`
returns a `sheenFree` reading of the largest blob (window count re-run confined
to the box, so its approximated solidity is measured on what survives) and the
rescue is gated on aspect identically. `153435918` is untouched because in the JS
it never fails on shape at all: its approximated solidity reads 0.998 and only
the window count holds it back, so the rescue never applies.

Two traps worth recording. `clipToBox()` can hand back the opposite winding and
`polyArea` is signed, so `fill` came out negative and the rescue silently never
fired; re-hulling the clipped points fixes it, the same thing `all` already does
for the crop outlines. And the trim fix swept as **"0 of 105 changed"** — a
single-card crop always warps to 1800 × 2867, so not one field `webdetect.py`
tracked could move. It now also records an 8×8 luminance thumbprint of the
output; recomputed on the two saved crops, 46 of its 64 cells differ, and it is
byte-stable across repeat runs of the same build. That is the third blind spot
this tool has had, each found by making a change on purpose and watching it
report nothing.

## 2026-08-24 — the phone app gets regression tests

`checleaner.py` has had assertions since the start; `checleaner.html` has only
ever had a sweep tool you diff by hand. `tests/test_web.py` closes that: the same
synthetic fixtures, pushed through the real page under Playwright, with
assertions on classification, crop geometry, the colour targets **measured on the
app's own output canvas**, glare handling and orientation. 13 tests, ~35 s.

A sweep diff and a test answer different questions. `webdetect.py --compare`
reports what *moved*; it cannot tell you the app was already wrong, and it has
been blind three separate times to changes that moved no field it tracked.

### Pushing the fixtures through both implementations first

Before writing a single assertion, every fixture went through `checleaner.py`
and the page side by side. They agree almost everywhere, which is the useful
result — and the one disagreement is worth having written down:

| fixture | checleaner.py | checleaner.html |
|---|---|---|
| `single`, `single_upsidedown`, `single_glare`, `welded_glare` | single, 1800 × 2867 | same |
| `grid` | single? 802 × 1070 | single? 796 × 1060 |
| `pale_desk` | single? 1197 × 1676 | single? 1197 × 1676 |
| `row2` | aligned 1396 × 1046 | aligned 1396 × 1046 |
| `signed_row` | aligned 1042 × 782 | aligned 1038 × 778 |
| `staggered_pile` | **aligned 1008 × 1344** | **left whole 1200 × 1920** |

The pile is the known tilt gap: the app's `dominantTilt()` still averages blob
`minAreaRect` angles, so on a staircase it reads the *arrangement's* angle
(aspect 2.23) rather than the cards'; turning the frame by that opens blank
corners no crop fits inside, and align declines. It is pinned as a test rather
than skipped, so whoever writes the contour tracer finds it failing and updates
the note instead of leaving a stale claim behind.

### Every test was watched to fail

Seven deliberate breaks in `checleaner.html`, and which test fired:

| mutation | caught by |
|---|---|
| white target 238.8 → 225 | colour targets (2 tests) |
| never flip an upside-down card | orientation |
| solidity gate → 0 | classification, never-warps |
| glare rescue disabled | 4 tests |
| glare blob filter removed | stray-glare crop |
| window backstop disabled | classification, never-warps, flush-grid |
| paper-confined white anchor disabled | colour targets |

Two of those found nothing on the first pass, and fixing that is most of what
this entry is worth:

- **The window backstop had no fixture at all.** Nothing in the set reached
  `MULTI_WINDOWS`: the row has 2 windows, the pile 3, the grid 1. So
  `make_flush_grid` — n × n cards laid flush — which is the one arrangement that
  beats every shape test at once, because n rows of n cards is *exactly* a card's
  aspect and touching borders leave no seams: it measures aspect 1.599, fill
  1.000, solidity 1.000 in Python and 1.597 / 1.000 / 1.003 in the app. Only the
  9 photo windows give it away. `checleaner.py` had the same blind spot, so it
  got the same test.
- **The never-warps test read the caption, not the pixels.** With the solidity
  gate dropped, the grid *was* warped into a card — 1800 × 2867 — but the page
  captioned it only "orientation uncertain", so the verdict-based assertion
  sailed past. Now it asserts on the output's size, which is the fact; every
  cropped single warps to the same canvas.

One test also had to be honest about what it does *not* pin: disabling the
app's paper-confined white anchor leaves the `pale_desk` fixture inside
tolerance (the card fills enough of the frame that the brightest band is mostly
paper either way) — it is the plain `single` fixture that moves, to 241.0. The
docstring says so rather than claiming the confinement is under test.

### Smaller things this needed

`tools/webdetect.py` had `sys.exit` at import when Playwright was missing, which
a test module can't catch cleanly; that moved into `main()` so the import raises
and the suite skips. Its `--save` now always writes `.jpg`, since what comes off
the canvas is JPEG whatever the source was called. And `make_single_with_glare`
is now one call to a shared `add_glare()`, because the second glare fixture was
written with a smaller ellipse that fell under the 3 %-of-frame blob threshold —
so it silently tested nothing until the mutation run caught it.

## 2026-08-24 — checleaner.html gets a contour tracer

The app had no ordered outline, and two things were built around the gap: its
`solidity` was approximated from pixel counts, and its tilt came off a fitted
rectangle. `traceContour()` (Moore-neighbourhood walk of a blob's outer
boundary, the same thing `cv2.findContours(..., RETR_EXTERNAL)` returns) plus
`dpSimplify()`/`approxPoly()` (Douglas-Peucker, `cv2.approxPolyDP` with
`closed=true`) close it, and `edgeDirs()` + `circularTilt()` are then direct
ports of `_edge_dirs()` and `_circular_tilt()`.

Both halves landed, but not with the payoffs the next-steps note predicted.

### The tilt: this is where the value was

`dominantTilt()` now reads the angle off the prints' own edges, gated on
`TILT_COHERENCE`, falling back to the blob rectangles below it. Measured against
`checleaner.py`'s `align_tilt` over the 65 photos of `main/` + `rancheki/` that
both implementations align:

| | mean \|JS − Python\| | worst |
|---|---|---|
| before | 0.154° | 0.510° |
| after | **0.058°** | **0.160°** |

34 files moved closer, 2 moved further (by 0.12° and 0.16°, noise). The
`staggered_pile` fixture — pinned in `tests/test_web.py` as a known divergence
two days ago — now crops to **1008 × 1344**, the same shape `checleaner.py`
produces, instead of being declined because the staircase's angle opened blank
corners no crop could fit. That test is now an agreement test.

Three files changed verdict on the sweep. `222119103` gained a crop, matching
Python. `234344460` and `002059642` lost one — but both were cropping *two
pixels* off their source (2974 × 3965 from 2976 × 3969), so "left whole" is the
same picture; they sit right on `place()`'s edge and a hundredth of a degree
tips them either way.

One wiring trap cost an hour: `process()` rebuilds each detection for the
full-resolution frame (`detsFull`) with only `quad`, `hull` and `area`, so the
new `edges` were silently dropped and `dominantTilt()` fell back every time.
Everything still worked, slightly worse than before, with no error anywhere.

### The solidity: the approximation was already right

`solidity` is now `polyArea(contour) / polyArea(hull(contour))` — literally
Python's `contourArea(contour) / contourArea(hull)`. Across 126 photos **no file
moved by more than 0.007**. The old `closedArea / hullArea` was accurate; its
only real defect was being a pixel count over a polygon area, which let it read
**above 1.0** on three files, so the number `MULTI_WINDOWS`'s companion
threshold was set against wasn't quite the quantity it named. Now it is, and it
is bounded by construction — `tests/test_web.py` asserts that outright.

### And the thing it was supposed to fix, it can't

The premise was that the app reads the staggered row `153435918` as a clean card
(0.995/0.998) because its solidity can't see the row's notches, and that a real
contour would drop it to Python's 0.863/0.793 and free `MULTI_WINDOWS` to be
split the way Python's is. With a real contour the file measures **0.994**.

Rendering both masks side by side explains it: **the app is not wrong.** Its
blob for that photo genuinely is a clean rectangle. Python's is not, because
Python's segmentation welds a patch of desk sheen onto it — the blob's bbox
starts at (0,0), and `_sheen_free_bbox` finds one sheen piece of 11 k px at 323
mean Scharr. It is that appendage, not the staggering, that costs Python's shape
test. The two masks differ by a pixel or two inside a 43-px close: the same
close bridges the sheen on one decoder's pixels and not on the other's.

So the four files passing the JS shape gate still interleave exactly as before —
6 windows: one real row and one genuine single; 7 windows: one genuine single
and one real row — and `MULTI_WINDOWS` stays 6 for both JS gates. The
conclusion in `docs/PIPELINE.md` § 3 was right; the reason given for it was
wrong, and is now corrected. Two genuine singles are still levelled rather than
cropped in the app, and that is not a contour problem.

### Also

`tools/webdetect.py` was labelling from the page's prose, which lies by
omission: a cleanly cropped single that also raises "orientation uncertain"
shows *only* the warning, so two of them were being filed as `other`. It now
reads `lastDetection.cropped` / `.aligned` instead.

## 2026-08-24 — the browser's FaceDetector: asked, answered, no

Content reorientation is the last thing `checleaner.py` does that the app
doesn't, and the cheapest imaginable way to close it was the browser's own
`FaceDetector` (Shape Detection API): no model, no WASM, nothing to cache,
offline from the first run. Chrome on Android had shipped part of that API and
the phone in question is a Pixel, so it was worth ten minutes before anything
heavier got built.

`web/facedetect-probe.html`, published so it could be opened on the device:

```
FaceDetector in window : false
isSecureContext        : true
origin                 : https://ganbaramen.github.io
userAgent              : ... Android 10; K ... Chrome/151.0.0.0 Mobile Safari/537.36
```

Not present. The face half of Shape Detection never shipped unflagged, and a
flag is not something an app can depend on. So the probe never got as far as the
question it was really built to answer — whether a `DetectedFace` carries a
*confidence*, which decides whether `content_rotation()`'s scoring maths ports
at all or has to be re-derived from face counts. That question is still open,
and only matters if some other detector ends up being used.

Probe deleted, as designed; the finding is in `CLAUDE.md`'s next steps so nobody
spends the same ten minutes again. Two routes remain, and the note now ranks
them: per-print border asymmetry (no model, works on `file://`, costs nothing —
`orientation()` already uses that signal for a single card) ahead of
onnxruntime-web plus YuNet (hosted-only, a few MB, and it takes
`tools/webdetect.py` off the `file://` path it currently drives).

Worth recording separately: **offline was never the obstacle.** `web/sw.js`
precaches `SHELL` on install, so anything added there is downloaded once and
kept. The real constraint is `file://` — an opaque origin can't `fetch()`
sibling files, so no WASM runtime loads there however well cached.

## 2026-08-24 — border asymmetry can't pick the turn either

With the browser's `FaceDetector` ruled out (above), the cheapest remaining
route to content reorientation in the app was geometry with no model at all. An
instax has a 4 mm border above its picture and a 20 mm signature border below,
and `orientation()` already reads exactly that to stand a *single* card up. On a
levelled multi-print frame every print carries the same asymmetry, and
`count_windows()`'s flood fill already finds each window — so walk out of each
window until the paper ends, call the long side that print's "down", and let the
prints vote.

Measured before writing any app code, against the `reorient` column of
`report.csv` (what the face detector chose) over 81 multi-print frames.
`tools/orientcheck.py`.

**It doesn't work, and the reason is structural.** The first attempt walked
until the paper ended and produced runs of 261, 284 and 587 px where a real
20 mm border is about 58: in a merged blob the paper is *continuous across
cards*, so "distance until the paper ends" is a property of the pile, not the
print. Two corrections — cap the walk at a fraction of the window's own short
side, and compare opposite pairs rather than all four directions (a card in a
row has free top and bottom but neighbours left and right, and the capped
neighbour distances otherwise win outright) — and it still doesn't separate:

| CAP | RATIO | abstain | right | wrong |
|---|---|---|---|---|
| 0.75 | 2.5 | 15 | 36 | **30** |
| 0.75 | 4.0 | 40 | 19 | 23 |
| 0.60 | 2.5 | 24 | 28 | 30 |
| 0.60 | 4.0 | 50 | 16 | **16** |
| 1.00 | 2.5 | 12 | 38 | 32 |

Tightening the ratio converts votes into abstentions without improving the odds
of the votes that remain — at 0.60/4.0 it is 16 right against 16 wrong, a coin
flip. And the bar here is not "mostly right": of 62 frames that were already
upright, the best setting **turns 24 of them wrongly**, which is the one mistake
`content_rotation()`'s whole conservative margin exists to prevent. Missing a
rotation costs a review; inventing one corrupts a photo that was right.

Breaking accuracy down by how crowded the frame is says exactly where it fails:

| prints in frame | right | wrong |
|---|---|---|
| 1–2 | 2 | 0 |
| 3–5 | 12 | 16 |
| 6+ | 22 | 14 |

The signal survives only while a card's borders are genuinely free. From three
prints up it is noise — and multi-print frames are, by definition, the crowded
case.

**So this route is not an alternative to per-print segmentation; it is blocked
behind it.** To measure one card's border you have to know where that card ends,
which is the "split multi-print photos" next step. If that ever lands, rerun
`tools/orientcheck.py` — the estimator is kept there for exactly that reason,
and the scoring half (ground truth, the upright-frames-turned-wrongly count, the
crowding breakdown) is reusable by whatever replaces it.

## 2026-08-25 — content reorientation ported to the phone app

The last thing `checleaner.py` did that the app didn't. Two cheaper routes were
measured and rejected first (the two entries above), leaving onnxruntime-web
plus the same YuNet model.

**Result: the app's turns agree with `checleaner.py` on 126 of 126 photos**, and
it now turns 19 frames by itself that previously needed the rotate buttons.

### Scoped before building, twice

The ONNX has a hard-coded `[1,3,640,640]` input where `cv2.FaceDetectorYN`
reshapes the network per frame, so a browser has to squash every frame into a
square first. Rather than discover that after a day's work, it was tested in
Python: force the square, rerun the decisions. **80 of 81 frames decide the
same** — not fatal, so the route was worth taking.

Sizes were measured too, since the answer decides delivery: `ort.min.js` 0.52 MB
plus `ort-wasm-simd.wasm` 10.06 MB at the last version that still ships a
non-threaded build (1.20 dropped it, and threads need COOP/COEP headers Pages
can't set). MediaPipe was no smaller (9.3 MB); TF.js is far smaller but its
short-range face model is built for selfies, not for faces inside a photo of
photos.

### The split: CDN the runtime, commit the model

10.6 MB is too much to put in git history forever, so `onnxruntime-web` comes
from jsdelivr at a pinned version and `web/sw.js` precaches it — one online
launch, offline thereafter, undone by deleting a few lines. The 232 KB model
*is* committed: it has to stay byte-identical to `checleaner.py`'s (verified by
hash), and the only CDN that serves it is an LFS redirect, which is a poor thing
for a service worker to depend on. jsdelivr's copy of the zoo is a 131-byte LFS
pointer, which would have been a confusing failure to debug later.

One thing that needed care: the service worker's fetch handler returned early
for anything cross-origin, so the runtime would have gone to the network every
time and the app would have quietly stopped working offline. It has a branch for
the pinned prefix now. And the precache of the big files is deliberately *not*
awaited into install's success — a CDN hiccup shouldn't stop the app installing,
it should just mean reorientation waits for the next online launch.

### YuNet's post-processing, reimplemented

`cv2.FaceDetectorYN` hides it; onnxruntime hands back 12 raw tensors. So
`yunetFaces()` does what OpenCV does internally: one prior per feature cell at
strides 8/16/32, score = `sqrt(cls * obj)`, box decoded relative to its cell,
then NMS — the boxes exist only so overlapping detections of one face can be
suppressed before the scores are summed.

Verified against Python before touching the app: per-turn scores match to about
0.01 across six frames, the difference being canvas resampling against
`cv2.resize`. The one apparent mismatch was a single face straddling the 0.6
score threshold, with both implementations agreeing on the winning turn anyway.

Two deliberate differences, both forced and both measured: the app scores the
*corrected* frame (it has already built that canvas by the time it knows the
frame is multi-print, and re-deriving the raw one means a second full decode on
a phone), and the square input above. Over 81 frames the decisions still match
on 79, and **both differences are abstentions rather than wrong turns** — the
direction it has to miss in.

### A four-month-old bug that only a 90° turn could expose

Folding the turn into `alignMulti()`'s warp made every crop candidate fail to
place. `invMap`, which maps a candidate crop back through the inverse rotation
to check it stays inside the photo, had the sign of `b` wrong in both the matrix
and the offset: it applied the rotation a *second* time instead of undoing it.

It survived since the align port because every tilt in this library is under 2°,
where `b < 0.035` and the round-trip error is ~14 px — inside the slack
`place()` already allows. At 90° it is **3605 px**. Fixed, and pinned as
arithmetic in `tests/test_web.py` rather than through a fixture, because the
only input that exposes it is one the fixtures don't produce.

Fixing it moved 10 files on the `file://` sweep independently of any of this,
and slightly *toward* `checleaner.py`: crop labels matching the reference went
106 → 107 of 126, with two frames gaining the crop Python gives them and one
correctly giving one up.

### Testing what only exists over http

`file://` is an opaque origin and can fetch neither the runtime nor the model,
so the app declines there — which also means the default `webdetect.py` sweep
cannot see this half of the app at all. Hence `--serve`: it assembles the same
`_site` the Pages workflow builds and drives that, so what is tested is what
ships. `tests/test_web.py` uses it for two new tests, skipped when the CDN is
unreachable, covering both halves of the contract — the five known-sideways
frames get stood up, and the frames already upright are left alone.

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
