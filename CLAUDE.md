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
  tests/test_pipeline.py regression tests: colour targets, aspect, orientation, single-vs-multi
  web/                   PWA assets (manifest, service worker, icons) for the hosted app
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
```

`--compare` prints only the files whose verdict moved, which is how you sweep
before changing a JS threshold — the JS ones (`MULTI_WINDOWS`,
`CARD_EDGE_SHARP`) are calibrated separately from Python's and can't be reasoned
about from the Python side. It tracks output **dimensions**, **white** and
**gain** as well as the labels: a geometry change routinely moves the pixels
while every caption stays identical, and a colour change moves neither the
pixels' count nor any label. Both gaps were found the same way — by making a
change on purpose and watching the tool report nothing.

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
  Python-only** — `checleaner.html` keeps one threshold (6) because its
  approximated solidity can't see a staggered row's notches, so the count is the
  only thing stopping one being cropped as a card. Don't "finish the port".
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

1. **Extend the regression tests to `checleaner.html`.** `checleaner.py` is
   covered by `tests/test_pipeline.py` (synthetic fixtures asserting colour
   targets, aspect, orientation, single-vs-multi); the phone app still has no
   assertions. The driving half is already done — `tools/webdetect.py` loads the
   page, feeds it files, and reports `kind`/`crop`/`size`/`white`/`gain`/
   `aspect`/`fill`/`solidity`/`glare`/`windows` — so what's left is feeding it the
   synthetic fixtures and asserting on those numbers, rather than only diffing
   two sweeps by hand. Optionally add real-photo golden numbers from
   `docs/HISTORY.md` to the opt-in tier.
2. **Give `checleaner.html` a face detector for content reorientation.**
   Levelling, the best-fit `CROP_ASPECTS` crop, the photo-window backstop
   (`countWindows()`), solidity, the desk-glare blob filter, the sheen trim
   (`sheenFreeBox()`), the lopsided-crop rule, and the paper-confined white
   anchor are all now ported (see `docs/PIPELINE.md` §§ 1, 3, 6) — window
   counts, `MULTI_WINDOWS` and `CARD_EDGE_SHARP` are calibrated separately from
   Python's, since canvas image decoding isn't pixel-identical to `cv2`'s.
   Desk *matching* has never existed in the app and can't: the target is a
   folder-wide median, and the app sees one photo at a time. What's still
   desktop-only besides that is `content_rotation()`: the app
   offers manual ⟲/⟳/180° rotate buttons instead, since the offline
   single-file page can't ship a face model. Closing the gap would need a JS
   face detector (e.g. onnxruntime-web + the same YuNet model), which also
   means solving how a `file://` page loads WASM offline (the hosted build has
   a service worker to lean on; see Hosting).
3. **Give `checleaner.html` a contour tracer.** It has none, and two separate
   gaps come out of that. Its `solidity` is approximated (`closedArea /
   hullArea`), so it reads a staggered row as a clean card —
   `153435918` measures 0.995/0.998 against Python's 0.863/0.793 —
   which leaves the window count as the only thing keeping such a row out of
   the single-card path, which is why `MULTI_WINDOWS` can't be split the way
   Python's now is, and why two genuine singles come out levelled rather than
   cropped (`docs/PIPELINE.md` § 3). And `dominantTilt()` still averages blob
   `minAreaRect` angles, so a staggered pile levels by its staircase rather
   than its cards, the way `checleaner.py` did before `_edge_dirs()`
   (`docs/PIPELINE.md` § 6) — which needs an outline to walk. One tracer plus
   a Douglas-Peucker pass fixes both; `TILT_COHERENCE` would then need its own
   sweep, since canvas decoding isn't pixel-identical to `cv2`'s.
4. **Split multi-print photos into separate crops.** Still balanced as one
   image even after alignment. The detector already returns every blob
   (`detect_all_prints()`); the work is handling prints that touch and merge
   into one blob.
