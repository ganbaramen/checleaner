# CLAUDE.md — checleaner

Photos of instax mini prints (chekis) lying on a desk, shot with a Pixel. Two jobs:
make the whites and blacks consistent across the whole collection, and — for photos
holding a single print — deskew, crop and rotate it upright.

Read `docs/PIPELINE.md` before changing any of the maths. Read `docs/HISTORY.md`
for what has already been processed and what the numbers came out at.

## Layout

```
checleaner/
  checleaner.py          batch CLI (desktop) — the reference implementation
  checleaner.html        single-file phone app, same pipeline ported to JS
  CLAUDE.md              this file
  README.md              project overview
  docs/PIPELINE.md       the algorithm, why each step is the way it is
  docs/HISTORY.md        every batch processed, with before/after measurements
  tools/detect.py        fast detection-only preview for named files (no colour pass)
  tools/webdetect.py     the same, for checleaner.html — drives the page under Playwright
  tools/orientcheck.py   scores an orientation estimator against report.csv's own answers
  tests/test_pipeline.py regression tests for checleaner.py
  tests/test_web.py      the same, for checleaner.html — drives the page under Playwright
  web/                   PWA assets (manifest, service worker, icons) for the hosted app
  web/face_detection_yunet_2023mar.onnx  the face model, MIT, identical to checleaner.py's
  .github/workflows/pages.yml  publishes checleaner.html to GitHub Pages over HTTPS
  chekis/                source photos, gitignored — never committed
    main/                 most photos land here
    <other>/               ad hoc structure for a specific shoot, e.g. rancheki,
                            sova_song_chekis — created as needed, not a fixed set
```

Source photos are never modified in place. Output goes to `balanced/` (and
`review/` for the CLI) inside each batch folder, keeping the original filename.

## Running

```bash
pip install numpy opencv-python pillow scipy piexif
python3 checleaner.py chekis/main/            # -> balanced, review, report.csv inside it
python3 checleaner.py chekis/main/ --dry-run  # measure and report, write nothing
python3 checleaner.py chekis/main/ --force    # reprocess everything, not just new files
```

A file already in `balanced/` or `review/` is skipped by default — its prior
`report.csv` row (kind, flags, geometry stats) is reused, and its measurement
(white/black/gain/desk) is read back from `report.csv` rather than recomputed —
the pipeline is deterministic, so redoing either would produce byte-identical
output. This is why folders don't need separate pending/done directories: just
drop new photos in and rerun; only the new ones (or a file present in *neither*
output dir, or — if something went wrong — present in *both*) get measured or
reprocessed. On a folder of 66 where only one file changed, that is the
difference between "measuring 1 of 66 images (65 unchanged, reusing prior
measurements)" and redoing the ~3 s/photo measurement pass for all 66; the
~10 s/file crop-and-colour pass was always this selective. Pass `--force`
after a code or calibration change, so every file benefits rather than just
new ones — it ignores `report.csv` entirely and remeasures + reprocesses from
scratch. (An older `report.csv` written before this caching existed has no
`desk` column; the next non-`--force` run measures every file once more to
backfill it, then caches normally from there.)

When you're iterating on *detection* geometry (which blob is a card, its aspect,
which way up, one print vs several) rather than colour, don't rerun the batch —
the whole-batch measurement pass dominates and detection doesn't need it. Run
`tools/detect.py <files…>` to get run()'s single/single?/multi verdict on just the
files you name, sub-second each; `--crop DIR` also writes the oriented crop of any
single-card hit (warped from the raw photo — colour never moves a pixel) so you
can eyeball orientation. It reuses `build_parser()`'s default thresholds so the
preview can't drift from a real run.

`--sheen` adds the numbers behind `CARD_EDGE_SHARP`: every paper piece in the
blob with its own boundary sharpness, and the trimmed box that results. That
threshold is the one you can't check by looking at a crop — card and sheen both
yield a plausible rectangle — so read the gap between the two classes instead of
assuming it. It's also the ground truth the JS port is calibrated against.

`report.csv` records every measurement and flag, including for files that
passed — check it rather than assuming a clean run means clean output. Its
`dest` column says `balanced` or `review` outright (derived from the flags, so
it can't drift out of sync with where the file actually landed);
`review/report.txt` lists just the flagged files and why, next to the photos
themselves — meant to be readable without watching console output, which
matters when a run is driven by an agent rather than a terminal.

Not every flag sends a photo to `review/`. Ones listed in `REVIEW_NOTES` are
**notes**: recorded and printed, but the file still lands in `balanced/`
(`_needs_review()`). `review/` is for outputs likely to be *wrong*, and a check
that fires on good ones costs attention and buys nothing — measured against
`chekis/main/`, the two notes fired on 10 photos and every one was fine. See
`docs/PIPELINE.md` § 7 before promoting or demoting one; the answer comes from
looking at what actually fired, not from taste.

`tests/test_pipeline.py` pins the numbers for `checleaner.py`: colour targets
(white 238.8, black 2.2), single-card aspect, the orientation flip, and the
single-vs-multi decision. Fixtures are synthetic and generated in-process — the
real photos are personal and gitignored — with an opt-in tier that also asserts
on `chekis/main/` when it's present and skips otherwise. Run it standalone
(`python3 tests/test_pipeline.py`, needs only checleaner's own deps) or under
`pytest tests/`. Run it after any change to the maths, not just the geometry.

`tests/test_web.py` pins the *port*, and it needs to exist separately because
passing Python tests say nothing about the app: it is a separate implementation
whose thresholds are calibrated against different pixels, and whose segmentation
does not always produce the same blob from the same photo. It builds the same fixtures, pushes them through the
real page under Playwright, and asserts on classification, crop geometry, the
colour targets **measured on the app's own output canvas**, the glare handling
and orientation. Three of its tests drive the page to a real **download**
instead, because the EXIF splice lives in the save handler and nothing else
reaches it — `webdetect.py --save` pulls pixels off the canvas and never presses
Save. Same commands; it skips cleanly when Playwright isn't
installed, so `pytest tests/` is safe either way — but it costs a browser launch
and a page load per fixture (~35 s) against test_pipeline's pure numpy.

Where the two implementations legitimately differ, `test_web.py` *pins the
difference* rather than skipping it, so closing a gap fails the test and gets
the note updated instead of leaving a stale claim in the docs.

Both suites were checked by mutation: break the app's white target, its
orientation flip, its solidity gate, its window backstop, its glare filter or
its glare rescue, and confirm which test fires. Two didn't, and that is how
`make_flush_grid` (nine cards laid flush — aspect 1.6, fill 1.0, solidity 1.0,
caught by nothing but the window count) and the stray-glare row fixture came to
exist. Do the same for any test added here; a test nobody has watched fail is
not yet a test.

The phone app is opened directly in a browser; there is no build step. To test
it headlessly, use `tools/webdetect.py` — the JS counterpart to
`tools/detect.py`. It drives the real page under Playwright (a dev-only
dependency: `pip install playwright && playwright install chromium`) and prints
the same kind of per-file verdict:

```bash
python3 tools/webdetect.py chekis/main/*.jpg              # sweep, one line each
python3 tools/webdetect.py --csv before.csv chekis/main/*.jpg
python3 tools/webdetect.py --csv after.csv --compare before.csv chekis/main/*.jpg
python3 tools/webdetect.py --save /tmp/js <files…>        # write the corrected frames
python3 tools/webdetect.py --serve <files…>              # over http, not file://
```

`--serve` assembles the same `_site` the Pages workflow builds and drives that.
It is the only way to exercise **content reorientation**: `file://` is an opaque
origin and can fetch neither the face runtime nor the model, so the app declines
there and a default sweep sees none of it.

`--compare` prints only the files whose verdict moved, which is how you sweep
before changing a JS threshold — the JS ones (`MULTI_WINDOWS`,
`CARD_EDGE_SHARP`) are calibrated separately from Python's and can't be reasoned
about from the Python side. Alongside the labels it tracks output
**dimensions**, **white**, **gain**, and an 8×8 luminance **thumbprint** of the
result. Each was added after the tool reported "nothing changed" for a change
made on purpose: a geometry change moves the pixels while every caption stays
identical, a colour change moves neither the pixel count nor any label, and a
single-card crop always warps to the same 1800 × 2867 — so for those, the
thumbprint is the *only* field that can move. Assume the next blind spot exists
and test for it the same way.

Two things to know before concluding the app has hung: the page has three
terminal states, not one (done, "couldn't find a white border", and thrown), and
it swallows JS exceptions while still showing a result — so a silent page error
looks like a clean run. `webdetect.py` waits on all three and reports page
errors loudly. There is still no *assertion* harness — see Next steps.

## Hosting

`.github/workflows/pages.yml` publishes `checleaner.html` as the GitHub Pages
site root, plus the `web/` PWA assets (manifest, service worker, icons), so the
app installs to the home screen over HTTPS and registers a Web Share Target for
the Android share sheet. The service worker caches the shell for offline use and
catches the shared-image POST.

The file at the repo root stays the single source of truth — **the workflow
copies, it doesn't fork**, so edit `checleaner.html` and never the published
copy. The `file://` path is unchanged by any of this: the PWA bits self-disable
off http/https, which is why `tools/webdetect.py` can drive the local file
directly.

## The two implementations

`checleaner.py` is the reference; `checleaner.html` is a port, and by now nearly
a complete one. Levelling, the best-fit `CROP_ASPECTS` crop, the photo-window
backstop, contour-traced solidity, the edge-direction tilt, the desk-glare blob
filter, the sheen trim, the lopsided-crop rule, the paper-confined white anchor
and content reorientation are all there. `MULTI_WINDOWS`, `CARD_EDGE_SHARP` and
`TILT_COHERENCE` are calibrated against the app's own pixels, not copied —
canvas decoding isn't `cv2`'s.

Two things are still desktop-only, for different reasons:

- **Desk matching never can be ported.** Its target is a folder-wide median and
  the app sees one photo at a time. Not a gap to close.
- **Content reorientation is off on `file://`.** An opaque origin can fetch
  neither the face runtime nor the model, so the app declines there and keeps
  its manual ⟲/⟳ buttons. Hosted, it works. This is why
  `tools/webdetect.py --serve` exists — the default `file://` sweep cannot see
  that half of the app at all.

**Two cheaper routes to reorientation were tried first and both failed; don't
re-propose them.** The browser's own `FaceDetector` is not present (Chrome 151
on Android, secure context, `false`) — the Shape Detection API's face half never
shipped unflagged. And per-print border asymmetry, which needs no model at all,
is a coin flip on real frames: in a merged blob the paper is continuous across
cards, so one print's border can't be measured without first knowing where that
print ends. See `tools/orientcheck.py` and the 2026-08-24 entries in
`docs/HISTORY.md`. The second becomes worth retrying only if the split-prints
next step lands.

## Invariants — do not change casually

- **White target 238.8, black target 2.2** (sRGB, 0–255). These are absolute, not
  per-folder. Every batch since the first is calibrated to them, so changing them
  silently de-matches the entire library. Both implementations must use the same
  numbers.
- **The white anchor is measured on the prints' own paper**, not the whole frame
  (`measure(..., paper=)` in both implementations, `docs/PIPELINE.md` § 1). It is
  what makes the balance independent of what the prints are lying on —
  frame-wide, a background brighter than the paper border silently becomes the
  white reference. Confirmed a no-op on the calibrated library (identical white
  on 137 of 140 files) precisely because the walnut is dark; do not assume the
  next background will be. Detection therefore has to run *before* the colour
  pass — that ordering is load-bearing. **Black stays frame-wide** — on this
  desk the darkest 0.5% is desk shadow and the 2.2 calibration depends on it.
- **All colour maths happens in linear light.** Gamma-space gain skews midtones.
- **instax mini is 54 × 86 mm** → aspect 1.5926, output 1800 × 2867.
- **Desk matching is secondary and damped** (strength 0.5, gamma clamped to
  `DESK_CLAMP` = [0.86, 1.16]). It must never be allowed to drag the prints'
  colour around. The clamp does double duty: a photo whose background the damped
  curve can't reach without being clipped is taken to be on a *different
  surface*, and is dropped from both the target median and the correction rather
  than given the largest gamma allowed (`desk_match=foreign` in `report.csv`, 6
  of 105 files in `chekis/main`). Keep that test relative to the batch — never
  hardcode what walnut looks like, or a permanent change of desk needs a
  recalibration instead of just working.
- **Scope is fronts.** Backs were handled once as an exception and are documented
  in `docs/PIPELINE.md`; the current code does not support them.
- **Multi-print reorientation is conservative by design.** `content_rotation()`
  (faces, `docs/PIPELINE.md` § 6) only turns a frame when the current orientation
  has weak face evidence *and* another turn is decisively better. Do not loosen
  that margin to catch a few more — its whole job is to never turn a frame that
  was already right. It also must stay a no-op when the model is missing.
- **`--multi-windows` (7) and `--card-windows` (8) are separate on purpose.**
  Overruling a *confident* single-card fit needs more evidence than overruling a
  near-miss, because the first mistake refuses to crop a real print and the
  second only refiles it. Do not collapse them: of 45 blobs passing the single
  gate, 44 are real cards reaching 7 windows and the 1 genuine pile also sits at
  7, so no shared threshold works. See `docs/PIPELINE.md` § 3. **This split is
  Python-only, and the app cannot have it** — `checleaner.html` keeps one
  threshold (6) because the window count is the only thing there stopping a real
  row being cropped as a card, and the two classes interleave on it: at 6
  windows sit one real row and one genuine single, at 7 the same pair again.
  Raising the bar for confident fits frees a row into the card-warping path.
  Don't "finish the port". (This used to be blamed on the app's approximated
  solidity; it isn't. See the 2026-08-24 contour-tracer entry in
  `docs/HISTORY.md` for what the real obstacle is.)
- **The sheen-free box is a second opinion in `detect_print`, never a
  replacement.** `single_fit()` retries the single-card gate on it only when the
  blob's *aspect* was what failed — a glare appendage distorts the fitted
  rectangle, while a blob that was already card-shaped and failed on
  fill/solidity is ragged, which is what a pile looks like from outside.
  Loosening that to any failure laundered a real 3-print row into a single card
  in the sweep. See `docs/PIPELINE.md` § 3.
- **Frame tilt comes from the prints' own edges**, not from a rectangle fitted
  to the blob and not from the photo windows (`_edge_dirs`, `docs/PIPELINE.md`
  § 6). Both alternatives fail on real photos in this library and fail
  *silently*: a staggered pile's fitted rectangle sits 33° off cards that are
  level, and a signature's ink loops make small square holes that read as
  perfectly level windows and outvote everything else — 81 of 140 files had
  their tilt decided that way. Both remain as fallbacks, behind
  `TILT_COHERENCE`, for frames whose edges genuinely disagree.
- **The detection thresholds are calibrated against the real library, not
  guessed** — `PRINT_FILL`, `CARD_OPP_MIN`/`CARD_AREA_MIN`/`CARD_SOLIDITY_MIN`,
  `MULTI_WINDOWS`, `CARD_WINDOWS`, `PAPER_HALO`, `TILT_COHERENCE`, and `--aspect-hi` (1.64, with
  real singles topping out at 1.631). Each sits in a measured gap between real cards
  and merged piles (see `docs/PIPELINE.md` § 3 and the 2026-08-16 entries in
  `docs/HISTORY.md`), and several are only a few points wide. Before moving one,
  sweep `chekis/main/` and check what reclassifies — the failure mode is silent:
  a pile cropped as a card comes out mangled, with nothing flagged.

## Conventions

- Match the existing docstring style: say *why*, not *what*. Several comments
  record a failure mode that cost real debugging — do not strip them.
- New confidence checks route to `review/` with a human-readable reason. Never
  silently drop or truncate work; if coverage is bounded, say so in the output.
- Verify changes by measuring, not by eyeballing thumbnails. The measurement
  snippet in `docs/PIPELINE.md` reproduces the numbers quoted in `docs/HISTORY.md`.
- When a crop looks wrong, check for mirroring first — see the winding gotcha.
- **Name a photo by the time part of its filename only** — `012024586`, not
  `PXL_YYYYMMDD_012024586.MP.jpg` — in comments, docs and commit messages. The
  time is unique across the whole library, so the date and extension are twenty
  characters of noise in a sentence already dense with numbers. Add the folder
  (`rancheki/053951339`) when the batch matters. Tests resolve these through
  `_photo()` in `tests/test_pipeline.py`; runnable example commands keep a
  `<file>.jpg` placeholder rather than a real dated path.

## Next steps, roughly in order of value

1. **Split multi-print photos into separate crops.** Still balanced as one
   image even after alignment. The detector already returns every blob
   (`detect_all_prints()`); the work is handling prints that touch and merge
   into one blob.
