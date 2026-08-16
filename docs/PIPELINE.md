# The pipeline

Five stages: **measure → balance → detect → crop → orient**. Each one below gives
the method, the constants, and — where it matters — the approach that was tried
first and why it failed. The failures are the useful part; several are non-obvious
and cost hours.

---

## 1. Measure

Three anchors, taken from a copy of the frame downscaled to 1100 px on the long edge.

**White — the print's paper border.** Pixels that are *bright and smooth*: above the
80th percentile of luminance, below the 25th percentile of local standard deviation
(9×9 window), and unclipped (max channel < 250). Take the per-channel median.

The smoothness test is doing real work. Plain "brightest pixels" grabs white
clothing inside the photo, which is bright but busy; flat paper border is the only
large smooth bright region. The unclipped test matters because a blown highlight
otherwise drags the estimate down and under-corrects.

**Black — the darkest content.** Mean of the pixels at or below the 0.5th
percentile of luminance. Content dependent (dark hair vs. deep shadow vs. the
film's own black), which is why the spread on the black point is always
looser than on the white. Must be *at or below*, not strictly below: a photo
with enough near-pure-black content (several dark-background prints, say) can
pile more than 0.5% of pixels onto the frame's true minimum, making that
minimum the percentile itself — a strict `<` then matches nothing, and a mean
of nothing is a NaN that silently poisons the whole correction.

**Desk — the surface.** Warm (R > B + 12), mid-dark (25 < luminance < 190),
low-texture (below the 45th percentile of local sd). Skin tones and warm clothing
inside a print leak into this mask; that leak is the reason the desk correction is
damped rather than exact.

## 2. Balance

Per channel, a gain and offset in **linear light** mapping white → 238.8 and
black → 2.2:

```
gain = (W_target - B_target) / (W_measured - B_measured)
off  = B_target - gain * B_measured
```

Then iterate. Applying the transform moves the very pixels the anchors were
measured from, so re-measure the corrected frame and nudge the working targets
until white is within 0.4% and black within 0.0004 (linear). Usually 1–3 passes.

Highlights get a **soft shoulder** (`tanh` above a knee at 0.90 linear) instead of
hard clipping. Without it, brightening a border turns paper texture into a flat
white slab.

The whole transform is a scalar function per channel, so it collapses into three
256-entry lookup tables. That is what makes applying it to a 12 MP frame cheap,
and it is how the phone version stays fast.

### Desk matching (secondary)

After levels, pull the desk toward the folder's median tone with a per-channel
**gamma**, not a second gain. Gamma fixes both endpoints, so the white and black
just set stay exactly where they are:

```
u     = (desk - B_target) / (W_target - B_target)      # normalised
gamma = log(target_u) / log(u), damped 50%, clamped to [0.86, 1.16]
```

Damped and clamped because the desk matters less than the prints, and because the
desk mask leaks skin tones. Disable with `--desk-strength 0`.

**What this cannot fix:** the desk's variation is mostly *lighting*, not colour
cast. Across a batch it typically halves the spread and no more. Two surfaces that
are genuinely different wood will never match — see the pine vs walnut case in
`docs/HISTORY.md`.

## 3. Detect the print

Both implementations find the card by its **white paper frame**: bright *and*
near-neutral, `L > 0.62 × p99(L)` and chroma < 16 (CIELAB). Close with r=21 to
bridge the photo window, open with r=8 to shed highlights, take the largest
connected component, convex hull, `minAreaRect`.

An earlier Python version instead segmented "everything that isn't desk" —
modelling the desk in CIELAB from a ring around the frame border and masking
pixels more than 5 normalised units away. It looked reasonable but was worse: a
print's dark photo area is often as dark and as warm as walnut, so that mask
came out as a hollow frame with any bright patch of desk merged into it. On the
same 11 photos the paper-frame method lands aspects at 1.568–1.611 against the
old method's 1.54–1.62 (and one photo the old mask fitted at 1.43). The paper
border is the more distinctive feature — bright and neutral is something desk
never is.

Accept the fit only if: exactly one large blob, aspect ∈ [1.53, 1.65], fill
≥ 0.93, **and solidity ≥ 0.97**. Fill is measured on the convex hull, so a
frame with an unfilled middle still scores ~1 — which is also the hole this
leaves open: a tight grid of several cards packed with almost no gaps can
*also* score high on both aspect and fill, since the grid's overall shape can
coincidentally land inside the single-card window. Solidity is the raw
contour area over the hull area, and catches what fill can't: real seams
between cards leave notches in the raw mask that only the hull smooths over,
so a genuine single card (no seams) has solidity essentially = 1.0, while a
merged grid measures noticeably lower — 0.94 on the one that motivated this,
against 0.99+ on every known-good single card checked. See `docs/HISTORY.md`
(2026-08-16) for the numbers.

If the fit fails and the aspect is *far* out of range, that is an ordinary
multi-print photo — balance it and leave it whole, no flag. Only a near-miss
(aspect 1.40–1.90, i.e. roughly card-shaped but failing the tight test) is worth a
human look, because that is what a genuinely bad fit looks like.

## 4. Crop

Perspective-transform the quad onto an 1800 × 2867 canvas. Not a rotated-rectangle
crop: the cards are photographed slightly off-axis and show real keystone. Forcing
the true 54 × 86 aspect corrects it.

### ⚠ Winding — the mirroring trap

The source quad and the destination rectangle must wind the same way. Get it wrong
and every output is horizontally mirrored, which is invisible on a portrait and
glaring the moment you read a signature. **This shipped twice during development.**

Do not hardcode `.reverse()`. Compute the signed area and normalise:

```js
windQuad(q)  // reverse iff signed area > 0; the destination winds negative
```

OpenCV's `boxPoints` and a hand-rolled `minAreaRect` do not agree on corner order,
which is exactly how the bug survived the port.

### Trimming desk out of the crop

Rectify provisionally, then scan each edge inward (capped at 3.5% of the
dimension) for lines that are desk-coloured. Test by projecting chroma onto the
desk's hue direction — shadow keeps the hue while losing lightness, so this
survives the shadow a card casts on its lee side.

Then **second-guess it with a different test**: a plain warm-and-dark check
(R > B + 12 and mean < 170) on the finished crop. Deliberately not the hue model,
so it does not share that model's blind spots. Skip the outermost 4 px — every
crop has a soft dark rim from the card edge and from resampling, and counting it
flags everything. Flag if desk reaches more than 15 px in.

**The desk's hue direction needs a real colour to point at.** It's derived from
the median colour in a ring around the *original photo's* outer edge, on the
assumption that's desk. When the card fills nearly the whole frame, that ring
can instead sample the card's own white border (or some other near-neutral
region) — the reference colour comes back essentially white, its "hue
direction" is short and arbitrary, and the projection test downstream turns
noise-sensitive enough to flag the border's own ordinary chroma jitter as
desk. Found via two overcropped outputs with the border trimmed to almost
nothing; both had a reference chroma magnitude (`nv`) around 2.0–2.24, while
every other file checked — the whole `chekis/rancheki/` fixture set plus the
rest of that batch — measured 3.6 or higher. Guarded: skip the trim entirely
below `nv = 4`, rather than trust a hue direction that thin. See
`docs/HISTORY.md` (2026-08-16).

## 5. Orient

Rotate so the wide signature border is at the bottom. The photo window sits
off-centre along the card's long axis (~5 mm one end, ~17 mm the other), so
locating the window says which way is up.

**Find the window by its EDGES, not its brightness.** Row-summed |∂/∂y| over the
central 60% of columns; the strongest peak in the top 45% and in the bottom 45%
are the window's two boundaries. Gap ratio comes out at **2.0–2.2** on real cards;
below 1.6, don't trust it and flag.

Two brightness-based attempts failed first, both instructive:

1. *First non-white row from the edge.* Finds the **signature** — dark ink written
   inside the wide border — not the photo. Got all 11 test photos upside down.
2. *Row where the non-paper fraction exceeds 70%.* Fixed the signature, still
   missed 4 of 11: prints whose own content is pale (a white wall behind the
   subject) read as paper.

Edges have neither problem. The window boundary is always a hard full-width line
regardless of what is in the picture or written on the border.

**The row profile is a low percentile across the row, not the mean.** Found via
a genuinely upside-down output with a *confident* wrong border ratio (2.07, well
above the 1.6 trust threshold): a mean row profile can be won by a strong but
partial-width edge inside the photo itself — here, a pale face against dark hair
— which has nothing to do with the border and can out-score the true transition
if the photo's own content is higher-contrast than the border edge at that row.
The 20th percentile across the row only scores high where the gradient is strong
almost everywhere across it, which a same-width content edge can't fake but the
genuine full-width border transition always satisfies. Verified against the true
edge by cropping and looking directly at the row it lands on, and re-verified
against all 12 known-good singles in `chekis/rancheki/` — identical flip decision
on every one, ratios shifting by hundredths.

## 6. Align multi-print photos

A multi-print photo isn't cropped to a card shape, but it can still be
straightened and centred: `align_multi()` in `checleaner.py`.

The **levelling** half (this section) is ported to `checleaner.html`
(`alignMulti()`, same tilt maths and footprint check). The **content
reorientation** half below is desktop-only — it needs a face model the offline
single-file app can't ship — so the phone app instead offers manual ⟲/⟳/180°
rotate buttons to stand a levelled result upright by hand.

**Rotation.** `detect_all_prints()` runs the same paper-frame segmentation as
single-print detection, but keeps every large blob instead of just the
biggest, and reports each one's `minAreaRect` tilt. A rectangle looks the same
every 90°, so tilt is folded into [-45°, 45°) before combining — two prints at
+44° and −44° are 2° apart, not 88°, and averaging the raw angles would get
that wrong. The frame is rotated by the **area-weighted circular mean** of
these tilts (weighted so a couple of small false-positive blobs can't outvote
the real prints), so as many prints as possible land parallel to the frame
edges.

**Crop.** After rotating (with the canvas expanded so nothing is clipped),
take the union bounding box of every detected blob in the rotated frame and
crop around it centred at the bounding box's own centre — centring there
makes the equal-margin requirement (top gap = bottom gap, left gap = right
gap) automatic for *any* crop size, not something to solve for separately.
The crop is then grown in whichever dimension the target aspect ratio (the
original photo's, unrotated) doesn't already pin, so it's the tightest crop
that both contains every print and matches that ratio.

**Bail out, don't force it.** If that ideal crop would reach past the real
photo into the blank corners the rotation opened up, `align_multi()` returns
`None` and the photo is left whole — today's existing behaviour. Checked by
mapping the crop's corners back through the inverse rotation and testing
they still land inside the original frame. This matters: these photos are
occasionally shot with prints laid out diagonally with barely any desk
margin (see `docs/HISTORY.md`), where a centred crop simply isn't possible
without padding that isn't there.

### What alignment cannot fix: landscape prints

`align_multi()` only rotates and crops the *whole frame*; it never touches an
individual print. That's fine for the frame-level tilt, but it means a photo
where the prints themselves are lying on their side — landscape content on
the (always-portrait) physical card — comes out level and centred but still
sideways, because nothing in this step looks at print content, only card
geometry, and card geometry alone can't tell portrait from landscape: two
landscape cards stacked and two portrait cards side by side land on the
*identical* merged aspect ratio, `86/54 × 2`.

Tried disambiguating this with the blob's long axis: a stack of K cards in
their tall direction should be vertical at `(86/54)·K`, a row of K upright
cards horizontal at `(54/86)·K`; landing on either formula with the *other*
edge direction would mean the cards are on their side. Verified against 3
known-sideways files — matched all 3 — then swept every multi/aligned file in
`chekis/main/` and found it also fired on grids of 10–13 correctly-oriented
cards, coincidentally landing near the same `k=2` ratio for reasons unrelated
to any card's orientation. ~30% precision on real data. Abandoned rather than
shipped even as a review flag — a flag wrong 7 times out of 10 trains you to
ignore it, which defeats the point. See `docs/HISTORY.md` for the numbers.

The lesson was that card *geometry* can't answer this — you have to read the
*content*, which is what the reorientation step below finally does.

### Standing the frame upright from content (faces)

Geometry gives level; it can't give up. So after `align_multi()` levels a
frame, `content_rotation()` reads the content to choose the remaining quarter
or half turn. Chekis are photographs of people, so the signal is faces: score
each of the four 90° turns by summed face confidence (OpenCV's YuNet detector)
and take the turn that stands the most faces upright. This is the same reason
`orient()` reads a single card's window instead of its geometry — the picture
knows which way is up when the outline doesn't.

Two things keep it from *introducing* errors, which matters because the vast
majority of multi-print frames are already upright and must not be touched:

- **A conservative margin.** A turn only wins over leaving the frame alone when
  the frame as-is has little face evidence *and* another turn is decisively
  better (`min_score` 1.2, `margin` 1.5×). A near-tie — one real file scored
  1.61 upright vs 1.82 for a half turn — is left alone, not flipped. Missing a
  rotation costs one review; inventing one corrupts a photo that was right.
- **Graceful absence.** The detector needs a small model (see below); if it
  can't be loaded, `content_rotation()` returns "no turn" and the frame is left
  exactly as `align_multi()` left it — the pre-face behaviour, never an error.

On `chekis/main/` this turned exactly the five known-sideways frames (four a
quarter turn, one a half turn, including the two-landscape-plus-four-portrait
mixed layout the geometry approach could never have split) and left all 44
other multi/aligned/`single?` frames untouched.

**Model.** YuNet, ~230 KB, cached under `~/.cache/checleaner/` and fetched from
the OpenCV Zoo on first use (override the path with `$CHEKI_FACE_MODEL`, or
disable the whole step with `--no-reorient`). This is the pipeline's one learned
component; everything else is classic CV. It lives only in `checleaner.py` — the
phone app doesn't do multi-print alignment at all yet.

---

## The backs exception (not in the current code)

One batch contained the *backs* of cards as well as fronts. Documented in case it
comes up again:

- A back has **no white border** — the brightest thing is the silver instax band,
  which is not white. Anchoring on it as if it were blew the images out (desk
  reached 183 on the first attempt).
- There *is* white: a narrow paper sliver at the extreme outer edge, top and
  bottom. Measure it as the p98 of unclipped pixels in the outer 3% of the crop.
- That sliver is often **partly clipped** (3–11% of band pixels). So: cross-
  calibrate the target against the fronts (both are the same paper, measured the
  same way) — it comes out at 1.1333 linear, i.e. above clipping — then **do not
  iterate the white**. It can never reach an unreachable target and the loop
  diverges to 7–13× gains. Solve the white once, iterate the black only.
- Backs have almost no paper margin on their long edges, so those sides run
  straight from film to desk with nothing to crop to. What looks like a desk
  sliver there is usually the card's own film surface — check at pixel level
  before "fixing" it.
- There is no equivalent of the wide-border trick for orienting a back; it would
  need OCR or template matching on the instax band.

---

## Verifying a change

Measure, don't eyeball. This reproduces the numbers quoted in `docs/HISTORY.md`:

```python
import glob, numpy as np
from PIL import Image
from scipy.ndimage import uniform_filter

def meas(f):
    im = Image.open(f); im.thumbnail((1400, 1400))
    a = np.asarray(im).astype(np.float32)
    lum = a.mean(2)
    m1 = uniform_filter(lum, 9)
    sd = np.sqrt(np.maximum(uniform_filter(lum * lum, 9) - m1 * m1, 0))
    w = (lum > np.percentile(lum, 80)) & (sd < np.percentile(sd, 25)) & (a.max(2) < 250)
    d = lum < np.percentile(lum, 0.5)
    return np.median(a[w], 0), a[d].mean(0)

ws, bs = zip(*(meas(f) for f in sorted(glob.glob('FOLDER/balanced/*.jpg'))))
ws, bs = np.array(ws), np.array(bs)
print('white', np.round(ws.mean(0), 1), 'sd', np.round(ws.std(0), 2))
print('black', np.round(bs.mean(0), 2), 'sd', np.round(bs.std(0), 2))
```

A healthy batch: white ≈ 239–240 on all three channels with sd ≈ 1–2, black ≈ 2–3
with sd < 1. If sd on white exceeds ~3, something regressed.
