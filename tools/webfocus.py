#!/usr/bin/env python3
"""Drive `focusmerge.html` headlessly -- the phone page's answer to tools/focusmerge.py.

`focusmerge.py` can be inspected from a REPL; `focusmerge.html` can only be
inspected by *running* it, and picking several files by hand in a browser does
not scale past one experiment. That makes threshold changes in the JS risky in
a way the Python ones are not: `FAST_T`, `MATCH_RATIO`, `REFINE_RESP` and the
rest are calibrated against this decoder rather than cv2's, so the only way to
know what a JS change does is to push real photographs through the real page.

    python3 tools/webfocus.py chekis/main/raw/*.jpg
    python3 tools/webfocus.py --save /tmp/js chekis/main/raw/*.jpg
    python3 tools/webfocus.py --csv before.csv chekis/main/raw/*.jpg
    # ... change a constant in focusmerge.html ...
    python3 tools/webfocus.py --csv after.csv --compare before.csv chekis/main/raw/*.jpg

Every file named is fed to the page in one go, as one merge, because that is what
the page is for -- unlike webdetect.py, where each file is its own run. To merge
several groups, invoke it once per group.

`--compare` prints only the fields that moved. Alongside the per-frame labels it
tracks the output **dimensions**, the **exposure gains** and an 8x8 luminance
**thumbprint** of the result, for the same reason webdetect.py does: a geometry
change moves the pixels while every caption stays identical, and a change to the
blend moves neither the pixel count nor any label, so for those the thumbprint is
the only field that can move.

Needs Playwright (`pip install playwright && playwright install chromium`), which
the pipeline itself does not -- this is a dev tool, not part of a run.

The page has three terminal states, not one: it can finish, it can report that
nothing lined up with the first shot, and it can throw. Waiting only for success
hangs on the second, and the page swallows exceptions into its status line, so a
silent JS error otherwise looks like a clean run. This waits on all three and
reports page errors loudly.
"""
import os
import re
import sys
import csv
import json
import base64
import pathlib
import argparse
import contextlib

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                     # reported by main(), not here
    sync_playwright = None

NEEDS_PLAYWRIGHT = ("this tool needs Playwright: "
                    "pip install playwright && playwright install chromium")

PAGE = pathlib.Path(__file__).resolve().parent.parent / "focusmerge.html"

# The three terminal states. `lastMerge` is set on success *and* on the
# nothing-lined-up path, so the status text is what tells them apart.
DONE = """() => {
  const s = document.getElementById('status').textContent;
  return /^done —/.test(s) || /nothing lined up/.test(s) ||
         /something went wrong/.test(s) || /at least two shots/.test(s);
}"""

READ = """() => {
  // bare name, not window.lastMerge: a top-level `let` in a classic script binds
  // in the global lexical environment and never becomes a property of window
  const m = (typeof lastMerge !== 'undefined') ? lastMerge : null;
  const out = { status: document.getElementById('status').textContent, reports: [] };
  if (m) {
    out.reports = m.reports.map(r => ({
      name: r.name, reference: !!r.reference, failed: r.failed || '',
      inliers: r.inliers || 0, matches: r.matches || 0,
      reproj: r.reproj || 0, share: r.share || 0,
      moved: r.moved || 0, worst: r.worst || 0,
      gains: r.gains || null }));
    out.note = m.scaleNote || '';
    if (m.out) {
      out.size = m.out.width + 'x' + m.out.height;
      // 8x8 luminance thumbprint: the only field that moves when a change alters
      // pixels without altering any caption or the output's dimensions
      const c = document.createElement('canvas'); c.width = 8; c.height = 8;
      const t = document.createElement('canvas');
      t.width = m.out.width; t.height = m.out.height;
      t.getContext('2d').putImageData(m.out, 0, 0);
      const cx = c.getContext('2d');
      cx.imageSmoothingQuality = 'high';
      cx.drawImage(t, 0, 0, 8, 8);
      const d = cx.getImageData(0, 0, 8, 8).data;
      let sig = '';
      for (let i = 0; i < 64; i++)
        sig += ((d[i*4]*29 + d[i*4+1]*150 + d[i*4+2]*77) >> 12).toString(16);
      out.sig = sig;
    }
  }
  return out;
}"""


def summarise(names, res):
    """One row for the merge: the page's own state, not its prose.

    Reads `lastMerge` rather than scraping the rendered text, for the reason
    webdetect.py learned the hard way -- the captions lie by omission, and a
    merge that also warns about movement shows only the warning.
    """
    status = res.get("status", "")
    reports = res.get("reports", [])
    used = [r for r in reports if not r["failed"] and not r["reference"]]
    row = {
        "files": " ".join(names),
        "frames": f"{len([r for r in reports if not r['failed']])}/{len(reports)}",
        "size": res.get("size", "-"),
        "inliers": ";".join(f"{r['inliers']}/{r['matches']}" for r in used) or "-",
        "reproj": ";".join(f"{r['reproj']:.2f}" for r in used) or "-",
        "share": ";".join(f"{r['share']:.2f}" for r in reports if not r["failed"]) or "-",
        # the colour half. Without it a change to the exposure match diffs as
        # "nothing changed" -- no label and no dimension is touched by it.
        "gains": ";".join(",".join(f"{g:.3f}" for g in r["gains"]) for r in used
                          if r["gains"]) or "-",
        "moved": ";".join(f"{r['moved']}@{r['worst']:.1f}" for r in used) or "-",
        "skipped": ";".join(r["failed"] for r in reports if r["failed"]) or "-",
        "note": res.get("note", "") or "-",
        "sig": res.get("sig", "-"),
        "status": "ok" if status.startswith("done") else status[:60],
    }
    return row


def run(files, save=None, quiet=False, timeout=600_000):
    if sync_playwright is None:
        raise RuntimeError(NEEDS_PLAYWRIGHT)
    errs = []
    with contextlib.ExitStack() as stack:
        p = stack.enter_context(sync_playwright())
        browser = p.chromium.launch()
        page = browser.new_page()
        page.on("pageerror", lambda e: errs.append(str(e)))
        page.on("console",
                lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
        page.goto(f"file://{PAGE}")
        page.set_input_files("#pick", [str(pathlib.Path(f).resolve()) for f in files])
        page.wait_for_function(DONE, timeout=timeout)
        res = page.evaluate(READ)
        row = summarise([pathlib.Path(f).name for f in files], res)
        if save:
            # The merged frame lives only on the canvas; the page's own Save
            # re-encodes it, so pull the pixels directly.
            uri = page.evaluate(
                "() => resultCanvas ? resultCanvas.toDataURL('image/jpeg', 0.95) : null")
            if uri:
                dst = pathlib.Path(save)
                if dst.is_dir() or not dst.suffix:
                    dst.mkdir(parents=True, exist_ok=True)
                    dst = dst / (pathlib.Path(files[0]).stem + "_merged.jpg")
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(base64.b64decode(uri.split(",", 1)[1]))
                if not quiet:
                    print(f"-> {dst}")
        browser.close()
    if not quiet:
        for r in res.get("reports", []):
            if r["reference"]:
                print(f"  {r['name']:<34} reference, {r['share']:.0%} of the result")
            elif r["failed"]:
                print(f"  {r['name']:<34} SKIPPED: {r['failed']}")
            else:
                moved = f"  MOVED {r['moved']} up to {r['worst']:.1f}px" if r["moved"] else ""
                g = ",".join(f"{v:.3f}" for v in r["gains"]) if r["gains"] else "-"
                print(f"  {r['name']:<34} {r['inliers']}/{r['matches']} inliers  "
                      f"reproj={r['reproj']:.2f}px  gain=({g})  "
                      f"share={r['share']:.0%}{moved}")
        print(f"  {'':<34} {row['size']}  {row['status']}"
              + (f"  [{row['note']}]" if row["note"] != "-" else ""))
    return row, errs


FIELDS = ["files", "frames", "size", "inliers", "reproj", "share", "gains",
          "moved", "skipped", "note", "sig", "status"]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="shots of one layout, merged together")
    ap.add_argument("--save", metavar="PATH", help="write the merged frame here")
    ap.add_argument("--csv", metavar="FILE", help="record the row for --compare")
    ap.add_argument("--compare", metavar="FILE", help="print what moved against this CSV")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    if sync_playwright is None:
        print(NEEDS_PLAYWRIGHT, file=sys.stderr)
        return 2
    if len(args.files) < 2:
        print("need at least two shots to merge", file=sys.stderr)
        return 2

    row, errs = run(args.files, save=args.save, quiet=args.quiet)
    if errs:
        print("\nPAGE ERRORS (the page hides these in its status line):", file=sys.stderr)
        for e in dict.fromkeys(errs):
            print("  " + e, file=sys.stderr)

    if args.csv:
        with open(args.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, FIELDS)
            w.writeheader()
            w.writerow(row)
    if args.compare:
        with open(args.compare) as fh:
            old = next(iter(csv.DictReader(fh)), {})
        moved = [(k, old.get(k, "-"), row[k]) for k in FIELDS
                 if k != "files" and old.get(k, "-") != row[k]]
        print("\ncompared with " + args.compare + ":")
        for k, a, b in moved:
            print(f"  {k:<9} {a}  ->  {b}")
        if not moved:
            print("  nothing moved")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
