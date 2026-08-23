#!/usr/bin/env python3
"""Drive `checleaner.html` headlessly -- the phone app's answer to tools/detect.py.

The desktop pipeline can be inspected from a REPL; the phone app can only be
inspected by *running* it, and opening a browser and picking files by hand does
not scale past about three photos. That makes threshold changes in the JS risky
in a way the Python ones aren't: `MULTI_WINDOWS` and `CARD_EDGE_SHARP` are
calibrated separately from Python's (canvas decoding isn't pixel-identical to
`cv2`'s -- see docs/PIPELINE.md § 3), so the only way to know what a JS change
reclassifies is to push every photo through the real page.

    python3 tools/webdetect.py chekis/main/*.jpg
    python3 tools/webdetect.py --csv before.csv chekis/main/*.jpg
    # ... change a threshold in checleaner.html ...
    python3 tools/webdetect.py --csv after.csv --compare before.csv chekis/main/*.jpg
    python3 tools/webdetect.py --save /tmp/js chekis/main/<file>.jpg

`--compare` is the one that matters: it prints only the files whose verdict
moved, which is what "sweep and check what reclassifies" means for the JS half.
A full sweep of `chekis/main/` takes a few minutes.

Needs Playwright (`pip install playwright && playwright install chromium`),
which the pipeline itself does not -- this is a dev tool, not part of a run.

Note the page has three terminal states, not one: it can finish, it can report
"couldn't find a white border in this photo" (two files in `chekis/main/` do),
and it can throw. Waiting only for success hangs on the second, which is worth
knowing before you conclude the app has locked up.
"""
import os
import re
import sys
import csv
import base64
import pathlib
import argparse

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                   # a dev-only dependency
    sys.exit("needs Playwright: pip install playwright && playwright install chromium")

PAGE = pathlib.Path(__file__).resolve().parent.parent / "checleaner.html"

# The page is done when it says so, has given up, or has fallen over -- all
# three are terminal, and waiting only on the first hangs for the timeout.
DONE = """() => {
  const t = (document.querySelector('#status') || {}).textContent || '';
  return t.startsWith('done') || t.includes("couldn't") || t.includes('failed');
}"""

READ = """() => ({
  status: (document.querySelector('#status') || {}).textContent || '',
  flags: (document.querySelector('#flags') || {}).textContent || '',
  stats: (document.querySelector('#stats') || {}).textContent || '',
  // The output's own dimensions, which no on-page label reports. Worth tracking
  // because a geometry change usually moves these *without* moving the crop
  // shape -- widening CROP_MARGIN took one frame from 2390x3186 to 2298x3064
  // and every other field stayed put.
  // (a bare identifier, not window.resultCanvas -- it is a top-level `let`,
  // which is script-scoped and never lands on `window`)
  size: typeof resultCanvas !== 'undefined' && resultCanvas
        ? `${resultCanvas.width}x${resultCanvas.height}` : '-',
  // the numbers the single/near-miss gates were decided on. Only the near-miss
  // flag text mentions aspect, so without this a sweep can't calibrate the
  // thresholds -- it can only see which side of them each file landed.
  det: typeof lastDetection !== 'undefined' ? lastDetection : null,
  // An 8x8 luminance thumbprint of the output. `size` catches a geometry change
  // only when the output's *dimensions* move, and for a single-card crop they
  // never do -- every one warps to the same 1800x2867. A trim that cut 53 px off
  // the top of a card diffed as "0 of 105 changed" without this. Quantised to
  // 64 levels so encoder jitter doesn't diff, which still leaves it sensitive to
  // any real shift of the pixels.
  sig: (() => {
    if (typeof resultCanvas === 'undefined' || !resultCanvas) return '-';
    const c = document.createElement('canvas');
    c.width = c.height = 8;
    const g = c.getContext('2d');
    g.drawImage(resultCanvas, 0, 0, 8, 8);
    const d = g.getImageData(0, 0, 8, 8).data, out = [];
    for (let i = 0; i < 64; i++) {
      const q = i * 4;
      out.push(Math.round((0.299 * d[q] + 0.587 * d[q+1] + 0.114 * d[q+2]) / 4));
    }
    return out.join('.');
  })(),
})"""

FIELDS = ["file", "kind", "crop", "size", "white", "gain", "aspect", "fill",
          "solidity", "glare", "windows", "prints", "tilt", "sig", "flags"]


def summarise(name: str, out: dict) -> dict:
    """The page's own words, reduced to the handful of fields worth diffing.

    `flags` keeps the aspect numbers stripped out: they wobble in the last
    decimal between runs of the same build, and a diff that fires on that is a
    diff nobody reads.
    """
    stats = " ".join(out["stats"].split())
    det = out.get("det") or {}
    status = out["status"].strip()
    flags = " ".join(out["flags"].split())

    def grab(pattern, default="-"):
        m = re.search(pattern, stats)
        return m.group(1) if m else default

    if "couldn't find a white border" in status:
        kind = "no-blob"
    elif "cropped, straightened" in flags:
        kind = "single"
    elif "couldn't fit one card" in flags:
        kind = "single?"
    elif "levelled" in flags:
        kind = "multi-aligned"
    elif "left whole" in flags:
        kind = "multi-whole"
    else:
        kind = "other"
    return {
        "file": name,
        "kind": kind,
        "crop": grab(r"crop shape(\S+?)(?:levelled|$)"),
        "size": out.get("size", "-"),
        # the colour half. Without these a change to the white/black anchors
        # diffs as "nothing changed" -- every geometry field is untouched by it.
        "white": grab(r"white before([\d, ]+?)white after"),
        "gain": grab(r"gain([\d., ]+?)clipped"),
        "aspect": f"{det['aspect']:.3f}" if det.get("aspect") is not None else "-",
        "fill": f"{det['fill']:.3f}" if det.get("fill") is not None else "-",
        "solidity": f"{det['solidity']:.3f}" if det.get("solidity") is not None else "-",
        # whether the single-card fit came from the glare-trimmed reading of the
        # blob rather than the blob itself -- a change here moves no other field
        "glare": "trimmed" if det.get("glareTrimmed") else "-",
        "windows": grab(r"photo windows(\d+)"),
        "prints": grab(r"prints seen(\d+)"),
        "tilt": grab(r"levelled(-?[\d.]+)°"),
        "sig": out.get("sig", "-"),
        "flags": re.sub(r"\(aspect [\d.]+\)", "(aspect N)", flags),
    }


def run(files, save=None, quiet=False):
    rows, errs = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console",
                lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
        for f in files:
            name = pathlib.Path(f).name
            page.goto(f"file://{PAGE}")
            page.set_input_files("#pick", str(pathlib.Path(f).resolve()))
            page.wait_for_function(DONE, timeout=180_000)
            row = summarise(name, page.evaluate(READ))
            rows.append(row)
            if not quiet:
                print(f"{name:<38} {row['kind']:<14} crop={row['crop']:<9} "
                      f"{row['size']:<10} windows={row['windows']:<3} {row['flags'][:60]}")
            if save:
                # The corrected frame lives only on the canvas -- the page's own
                # download button re-encodes it, so pull the pixels directly.
                uri = page.evaluate(
                    "() => resultCanvas ? resultCanvas.toDataURL('image/jpeg', 0.9) : null")
                if uri:
                    dst = pathlib.Path(save) / name
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes(base64.b64decode(uri.split(",", 1)[1]))
        browser.close()
    return rows, errs


def compare(rows, baseline_path):
    """Print only what moved since `baseline_path`, and say so if nothing did."""
    with open(baseline_path, newline="") as fh:
        before = {r["file"]: r for r in csv.DictReader(fh)}
    changed = 0
    for row in rows:
        was = before.get(row["file"])
        if was is None:
            print(f"{row['file']:<38} NEW  {row['kind']}")
            changed += 1
            continue
        moved = [k for k in FIELDS[1:] if was.get(k, "") != row[k]]
        if moved:
            changed += 1
            print(row["file"])
            for k in moved:
                print(f"    {k:<8} {was.get(k, ''):<28} -> {row[k]}")
    missing = [f for f in before if f not in {r["file"] for r in rows}]
    for f in missing:
        print(f"{f:<38} GONE (not in this run)")
    print(f"\n{changed} of {len(rows)} changed"
          + (f", {len(missing)} not rerun" if missing else ""))
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="image files to push through the page")
    ap.add_argument("--csv", metavar="OUT", help="write the verdicts as CSV for later --compare")
    ap.add_argument("--compare", metavar="BASELINE", help="print only what moved since this CSV")
    ap.add_argument("--save", metavar="DIR", help="write each corrected frame to DIR")
    args = ap.parse_args()

    missing = [f for f in args.files if not os.path.isfile(f)]
    if missing:
        sys.exit("no such file: " + ", ".join(missing))

    rows, errs = run(args.files, save=args.save, quiet=bool(args.compare))
    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, FIELDS)
            w.writeheader()
            w.writerows(rows)
        print(f"\nwrote {args.csv}")
    if args.compare:
        compare(rows, args.compare)

    # Page errors are the finding, not a footnote: the app swallows them and
    # still shows a result, so a silent JS exception looks like a clean run.
    for e in dict.fromkeys(errs):
        print("PAGE ERROR:", e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
