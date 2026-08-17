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
`dest` column says `balanced` or `review` outright (derived from whether
`flags` is empty, so it can't drift out of sync with where the file actually
landed); `review/report.txt` lists just the flagged files and why, next to the
photos themselves — meant to be readable without watching console output,
which matters when a run is driven by an agent rather than a terminal.

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
about from the Python side. It tracks output **dimensions** as well as the
labels, because a geometry change routinely moves the pixels while every caption
on the page stays identical.

Two things to know before concluding the app has hung: the page has three
terminal states, not one (done, "couldn't find a white border", and thrown), and
it swallows JS exceptions while still showing a result — so a silent page error
looks like a clean run. `webdetect.py` waits on all three and reports page
errors loudly. There is still no *assertion* harness — see Next steps.

## Invariants — do not change casually

- **White target 238.8, black target 2.2** (sRGB, 0–255). These are absolute, not
  per-folder. Every batch since the first is calibrated to them, so changing them
  silently de-matches the entire library. Both implementations must use the same
  numbers.
- **All colour maths happens in linear light.** Gamma-space gain skews midtones.
- **instax mini is 54 × 86 mm** → aspect 1.5926, output 1800 × 2867.
- **Desk matching is secondary and damped** (strength 0.5, gamma clamped to
  [0.86, 1.16]). It must never be allowed to drag the prints' colour around.
- **Scope is fronts.** Backs were handled once as an exception and are documented
  in `docs/PIPELINE.md`; the current code does not support them.
- **Multi-print reorientation is conservative by design.** `content_rotation()`
  (faces, `docs/PIPELINE.md` § 6) only turns a frame when the current orientation
  has weak face evidence *and* another turn is decisively better. Do not loosen
  that margin to catch a few more — its whole job is to never turn a frame that
  was already right. It also must stay a no-op when the model is missing.
- **The detection thresholds are calibrated against the real library, not
  guessed** — `PRINT_FILL`, `CARD_OPP_MIN`/`CARD_AREA_MIN`/`CARD_SOLIDITY_MIN`,
  `MULTI_WINDOWS`, `PAPER_HALO`. Each sits in a measured gap between real cards
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

## Next steps, roughly in order of value

1. **Extend the regression tests to `checleaner.html`.** `checleaner.py` is now
   covered by `tests/test_pipeline.py` (synthetic fixtures asserting colour
   targets, aspect, orientation, single-vs-multi). The phone app is still checked
   by hand — port the same asserted numbers to a Playwright-driven check so both
   implementations are safe to change. Optionally, add real-photo golden numbers
   from `docs/HISTORY.md` to the opt-in tier.
2. **Give `checleaner.html` a face detector for content reorientation.**
   Levelling, the best-fit `CROP_ASPECTS` crop, the photo-window backstop
   (`countWindows()`), solidity, the desk-glare blob filter, the sheen trim
   (`sheenFreeBox()`), and the lopsided-crop rule are all now ported (see
   `docs/PIPELINE.md` §§ 3, 6) — window counts, `MULTI_WINDOWS` and
   `CARD_EDGE_SHARP` are calibrated separately from Python's, since canvas image
   decoding isn't pixel-identical to `cv2`'s. What's still desktop-only is
   `content_rotation()`: the app
   offers manual ⟲/⟳/180° rotate buttons instead, since the offline
   single-file page can't ship a face model. Closing the gap would need a JS
   face detector (e.g. onnxruntime-web + the same YuNet model), which also
   means solving how a `file://` page loads WASM offline — see item 4.
3. **Split multi-print photos into separate crops.** Still balanced as one
   image even after alignment. The detector already returns every blob
   (`detect_all_prints()`); the work is handling prints that touch and merge
   into one blob.
4. *(done)* **Hosted over HTTPS on GitHub Pages** — `.github/workflows/pages.yml`
   publishes `checleaner.html` as the site root plus the `web/` PWA assets
   (manifest, service worker, icons), so it installs to the home screen and
   registers a Web Share Target for the Android share sheet. The service worker
   caches the shell for offline use and catches the shared-image POST; the
   `file://` path is unchanged (the PWA bits self-disable off http/https). The
   file at the repo root stays the single source of truth — the workflow copies,
   it doesn't fork.
