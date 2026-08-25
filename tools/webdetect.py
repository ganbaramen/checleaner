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

Don't edit `checleaner.html` while a sweep is running. Each file is a fresh page
load, so a mid-run edit is picked up from that point on and the CSV ends up half
one build and half another -- which reads exactly like a real reclassification.
(Cost an hour once, chasing a solidity that had "regressed" to 1.000 on twenty
files: a mutation-testing loop had been rewriting the page underneath it.)

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
import shutil
import pathlib
import argparse
import tempfile
import functools
import threading
import contextlib
import http.server
import socketserver

# A dev-only dependency, and an *optional* one: tests/test_web.py imports this
# module to drive the page and skips itself when the import fails, so the failure
# has to be catchable rather than a sys.exit at import time.
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

NEEDS_PLAYWRIGHT = "needs Playwright: pip install playwright && playwright install chromium"

REPO = pathlib.Path(__file__).resolve().parent.parent
PAGE = REPO / "checleaner.html"


@contextlib.contextmanager
def hosted_site():
    """Serve the app the way GitHub Pages does, and yield its URL.

    `file://` is an opaque origin: it can't fetch the face runtime or the model,
    so content reorientation is off there by design and a sweep over the local
    file can't see it at all. This assembles the same `_site` layout the Pages
    workflow builds -- checleaner.html as index.html alongside everything in
    web/ -- so what gets driven is what gets deployed, and the app's `./`
    relative paths resolve exactly as they will in production.
    """
    site = tempfile.mkdtemp(prefix="checleaner-site-")
    shutil.copy(PAGE, os.path.join(site, "index.html"))
    for f in (REPO / "web").iterdir():
        if f.is_file():
            shutil.copy(f, site)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=site)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/index.html"
    finally:
        httpd.shutdown()
        shutil.rmtree(site, ignore_errors=True)

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
          "solidity", "glare", "windows", "prints", "tilt", "turn", "sig", "flags"]


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

    # Read the page's own state, not its prose. The captions were the only thing
    # available before `lastDetection` existed, and they lie by omission: a crop
    # that also raises "orientation uncertain" shows *only* that warning, so two
    # cleanly cropped singles were being filed as "other".
    if "couldn't find a white border" in status:
        kind = "no-blob"
    elif det.get("cropped"):
        kind = "single"
    elif "couldn't fit one card" in flags:
        kind = "single?"
    elif det.get("aligned"):
        kind = "multi-aligned"
    elif det:
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
        # the content turn, which only exists when the page is served over http
        # (see --serve); on file:// it is always "-"
        "turn": str(det.get("reorient", "-")),
        "sig": out.get("sig", "-"),
        "flags": re.sub(r"\(aspect [\d.]+\)", "(aspect N)", flags),
    }


def run(files, save=None, quiet=False, serve=False):
    if sync_playwright is None:
        raise RuntimeError(NEEDS_PLAYWRIGHT)
    rows, errs = [], []
    with contextlib.ExitStack() as stack:
        url = stack.enter_context(hosted_site()) if serve else f"file://{PAGE}"
        p = stack.enter_context(sync_playwright())
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console",
                lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
        for f in files:
            name = pathlib.Path(f).name
            page.goto(url)
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
                    # always .jpg: what comes off the canvas is JPEG whatever the
                    # source was called, and a PNG fixture saved as `.png` here
                    # would be a JPEG lying about its name
                    dst = pathlib.Path(save) / (pathlib.Path(name).stem + ".jpg")
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
    ap.add_argument("--serve", action="store_true",
                    help="drive the app over http from an assembled _site instead of "
                         "file:// -- the only way to exercise content reorientation, "
                         "which an opaque origin can't load a runtime for")
    args = ap.parse_args()
    if sync_playwright is None:
        sys.exit(NEEDS_PLAYWRIGHT)

    missing = [f for f in args.files if not os.path.isfile(f)]
    if missing:
        sys.exit("no such file: " + ", ".join(missing))

    rows, errs = run(args.files, save=args.save, quiet=bool(args.compare),
                     serve=args.serve)
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
