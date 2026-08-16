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
  <batch folders>/       source photos, each with a balanced/ subfolder of output
```

Source photos are never modified in place. Output goes to `balanced/` (and
`review/` for the CLI), keeping the original filename.

## Running

```bash
pip install numpy opencv-python pillow scipy piexif
python3 checleaner.py FOLDER/            # -> FOLDER/balanced, FOLDER/review, FOLDER/report.csv
python3 checleaner.py FOLDER/ --dry-run  # measure and report, write nothing
```

~10 s per photo. `report.csv` records every measurement and flag, including for
files that passed — check it rather than assuming a clean run means clean output.

The phone app is opened directly in a browser; there is no build step. To test it
headlessly, drive it with Playwright: load `file://.../checleaner.html`, `setInputFiles`
on `#pick`, wait for `#status` to start with `done`, then read `#flags` and
`#stats`. There is no assertion harness yet — see Next steps.

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

## Conventions

- Match the existing docstring style: say *why*, not *what*. Several comments
  record a failure mode that cost real debugging — do not strip them.
- New confidence checks route to `review/` with a human-readable reason. Never
  silently drop or truncate work; if coverage is bounded, say so in the output.
- Verify changes by measuring, not by eyeballing thumbnails. The measurement
  snippet in `docs/PIPELINE.md` reproduces the numbers quoted in `docs/HISTORY.md`.
- When a crop looks wrong, check for mirroring first — see the winding gotcha.

## Next steps, roughly in order of value

1. **A regression test.** Both implementations are checked by hand right now.
   A fixture folder plus asserted white/black/aspect/orientation numbers would
   make any future change safe. The numbers to assert are in `docs/HISTORY.md`.
2. **Split multi-print photos into separate crops.** Currently they are balanced
   and left whole. The detector already counts blobs; the work is handling prints
   that touch and merge into one blob.
3. **Host `checleaner.html` over HTTPS** to make it installable to the home screen and
   available in the Android share sheet. A `file://` page can be neither.
