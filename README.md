# checleaner

Photos of instax mini prints ("chekis") lying on a desk, shot with a phone.
Checleaner does two jobs: make the whites and blacks consistent across the
whole collection, and — for photos holding a single print — deskew, crop and
rotate it upright.

Two implementations of the same pipeline:

- **`checleaner.py`** — batch CLI for the desktop, the reference implementation.
- **`checleaner.html`** — single-file phone app, same pipeline ported to JS.
  Open it directly in a browser; there's no build step.

## Usage

```bash
pip install numpy opencv-python pillow scipy piexif
python3 checleaner.py chekis/main/            # -> balanced, review, report.csv inside it
python3 checleaner.py chekis/main/ --dry-run  # measure and report, write nothing
```

~10 s per photo. Source photos are never modified in place — output goes to
`balanced/` (and `review/` for anything the CLI isn't confident about),
keeping the original filename. `report.csv` records every measurement and
flag, including for files that passed.

## Layout

```
checleaner/
  checleaner.py          batch CLI (desktop) — the reference implementation
  checleaner.html        single-file phone app, same pipeline ported to JS
  docs/PIPELINE.md       the algorithm, why each step is the way it is
  docs/HISTORY.md        every batch processed, with before/after measurements
  chekis/                source photos, gitignored — never committed
    main/                 most photos land here
    <other>/               ad hoc structure for a specific shoot
```

## Invariants

- **White target 238.8, black target 2.2** (sRGB, 0–255), absolute across the
  whole library — every batch since the first is calibrated to these numbers.
- **All colour maths happens in linear light.**
- **instax mini is 54 × 86 mm** → aspect 1.5926, output 1800 × 2867.
- **Scope is fronts.** Backs were handled once as an exception; see
  `docs/PIPELINE.md`.

See `docs/PIPELINE.md` for the algorithm and `docs/HISTORY.md` for every
batch processed so far, with the measurements each one came out at.
