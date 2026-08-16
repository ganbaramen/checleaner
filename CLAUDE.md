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

~3 s per photo for the (cheap) measurement pass, ~10 s more for any file actually
reprocessed. A file already in `balanced/` or `review/` is skipped by default and
its prior `report.csv` row reused — the pipeline is deterministic, so redoing it
would produce byte-identical output. This is why folders don't need separate
pending/done directories: just drop new photos in and rerun: only the new ones
(or a file present in *neither* or, if something went wrong, present in *both*
output dirs) get the expensive full-resolution pass. Pass `--force` after a code
or calibration change, so every file benefits rather than just new ones.

When you're iterating on *detection* geometry (which blob is a card, its aspect,
which way up, one print vs several) rather than colour, don't rerun the batch —
the whole-batch measurement pass dominates and detection doesn't need it. Run
`tools/detect.py <files…>` to get run()'s single/single?/multi verdict on just the
files you name, sub-second each; `--crop DIR` also writes the oriented crop of any
single-card hit (warped from the raw photo — colour never moves a pixel) so you
can eyeball orientation. It reuses `build_parser()`'s default thresholds so the
preview can't drift from a real run.

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

The phone app is opened directly in a browser; there is no build step. To test it
headlessly, drive it with Playwright: load `file://.../checleaner.html`, `setInputFiles`
on `#pick`, wait for `#status` to start with `done`, then read `#flags` and
`#stats`. There is no assertion harness for it yet — see Next steps.

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
2. **Catch `checleaner.html` up on multi-print handling.** Levelling
   (`align_multi()`) is ported as `alignMulti()`, but two later additions are
   not: the best-fit `CROP_ASPECTS` crop (tried in Python first — the JS still
   crops at the frame's own ratio) and content reorientation
   (`content_rotation()`) — the app offers manual ⟲/⟳/180° rotate buttons
   instead, since the offline single-file page can't ship a face model. Closing the gap would need a JS face detector
   (e.g. onnxruntime-web + the same YuNet model), which also means solving how a
   `file://` page loads WASM offline — see item 4.
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
