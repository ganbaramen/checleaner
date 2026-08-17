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

**"One large blob" means one card-shaped blob.** A specular highlight on the
desk is bright and near-neutral enough to survive segmentation as its own
component, and any second component used to break the `n_blobs == 1` test — so
four flawless single cards (aspect 1.577–1.585, fill ≥ 0.99) were being routed
down the multi-print path by a patch of desk glare. Glare is never rectangular
though: those blobs measured fill 0.78–0.82 against a real card's 0.99. Only
secondary blobs at `fill ≥ PRINT_FILL` (0.90) count toward the total, so the
largest blob always counts and a highlight never does.

`detect_all_prints()` has to drop glare too, and more urgently: `align_multi()`
crops around the **union** of every blob it returns, so one bright patch in a
corner drags the crop out to cover it and the photo declines as uncroppable.
Rectangularity alone can't decide it there, because a *pile* of scattered prints
is a single blob that fills its own bounding rect poorly — 0.844 on one photo,
barely above that photo's glare at 0.815. Size alone can't either, since a lone
card really can be small in frame. Together they can: a real card is always
rectangular, and a real pile is never small. A blob is kept if it is either
≥ 25% of the largest blob's area **or** `fill ≥ PRINT_FILL`.

**Glare merged *into* the print blob** is the hardest case: when the
segmentation close bridges a print to an adjacent desk sheen the two become one
blob, so no per-blob filter applies, and every crop drawn from that blob swells
to cover desk. `_sheen_free_bbox()` handles it, and what works is **how each
piece of paper ends**, not what it looks like inside: a card has a crisp edge
against the desk, a sheen fades into it. Splitting the unclosed paper into
pieces and scoring each piece's own boundary by mean Scharr magnitude puts sheen
at 235–350 against a card's 594–1511, so `CARD_EDGE_SHARP` (450) sits in open
space between them.

Three details are load-bearing:

- **Erode to split, then measure grown back.** Pieces often merely touch, and a
  few pixels parts them — but the boundary of an *eroded* piece sits in flat
  paper and scores low whatever it is, so each piece is dilated back to its true
  extent before its edge is judged.
- **Only a bounding box comes out of it.** The rectangle is still fitted to the
  *closed* blob trimmed to that box. Re-fitting it to the raw paper instead
  moves the quad even when nothing is removed, because that mask is fragmented —
  which showed up as two files shifting on a ~0% trim.
- **Distrust a big loss.** A sheen is an appendage, so cutting it leaves most of
  the blob standing; if less than `SHEEN_KEEP_MIN` of the bounding box survives,
  the edge test has rejected real cards and the whole answer is discarded (one
  photo kept a single 0.5% piece and its crop collapsed).

Six *interior* statistics were measured first and every one of them overlaps —
**don't reach for these again**: brightness (sheen is as bright as paper;
sweeping to `L > 0.85 × p99` barely moved the box), local variance (on a smooth
desk a sheen is as smooth as a border), edge-coverage trim (catches a
7 %-coverage fringe but these run 41–64 %), and three ways of anchoring on photo
windows — enclosed windows (fixes 2 files, trims 20–47 % off 4 others), any dark
region (no fixes, no regressions), photo-shaped dark regions (still trims 305 px
and 325 px off good files). They all fail for the same reason: windows are found
for only some cards, so "paper not near a window" is not "not a card". The
boundary is the one signal that doesn't depend on finding every window.

**Corners, not a bounding rectangle.** A card photographed at an angle is a
trapezoid, and `minAreaRect` can only circumscribe it — so it reads too wide
(real cards measured 1.485 and 1.506 against instax's 1.593, falling out of the
accept band entirely) and, handed to `warp` as the crop source, leaves the
perspective transform nothing to correct: it degenerates to an affine map, the
keystone survives, and desk spills in on the near edge. `_card_quad()` fits the
blob's four actual corners (`approxPolyDP`, loosening ε until it simplifies to
4 points) and those two files then measure 1.600 and 1.604. It is used only
when the fit really looks like one card seen at an angle — convex, opposite
sides within 3%, and filling ≥ 97% of its own bounding rectangle. Merged piles
score 0.52–0.90 on those, so a pile can't be quietly promoted to a card. When
no fit qualifies, the `minAreaRect` quad stands.

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

A card whose four corners fitted (above) gets a slightly gentler solidity floor,
`CARD_SOLIDITY_MIN` = 0.95: shot at an angle its mask edge comes out a little
raggeder, and two real ones measured 0.957 and 0.962. The relaxation is
deliberately small — the overlapping 2-print blob it has to keep out measured
0.916, and that blob *does* pass the corner test, so the corner fit alone is not
enough to admit a card.

If the fit fails and the aspect is *far* out of range, that is an ordinary
multi-print photo — balance it, no flag. A near-miss (aspect 1.40–1.90, i.e.
roughly card-shaped but failing the tight test) is worth a human look, because
that is what a genuinely bad fit looks like. That band reads the **blob's
`minAreaRect` aspect**, not the corner fit — it was calibrated against the
former, and switching it pulled photos that were classifying correctly as
multi-print into review for no gain.

A near-miss is still **levelled and cropped** like any other multi-print photo;
only the flag differs. Nothing available can tell a badly-fitted single card
from several prints overlapped into a card-shaped pile — window count, fill and
solidity all overlap between the two (the six near-misses in this library
measured 0–9 windows against genuine singles' 0–5) — and every near-miss here
turned out to be the latter. Leaving them whole was the visible cost: the crop a
multi-print photo deserves was withheld from all six. If the guess is wrong the
result is a levelled frame around one card rather than a mangled one, and the
flag still routes it to review, so the human look this band exists for is
unchanged.

**Overlapping prints** are the hard case, and a photo-window count is the
backstop. Prints laid over each other merge into one blob whose shape stats can
beat a real card's — white border on white border leaves no seam, so fill and
solidity see nothing (one 4-print row measured fill 0.988, solidity 0.991,
cleaner than some genuine singles) — but each print's *picture* stays dark and
separate, an enclosed hole in the paper mask. `count_windows()` counts those
holes: one card encloses one window, fragmented at most into a few pieces where
bright content bridges it to the border (worst genuine single in the library:
6 fragments), while merged multi-print blobs run 7–18. A blob with
`--multi-windows` (default 7) or more windows can't be one card, so it is
treated as the multi-print shot it is and sent down the align path.

This check guards **both** decisions, not just near-misses: a tidy row can slip
right through the tight single test (one real 3-print row landed aspect 1.639,
fill 0.994, solidity 0.992 — all inside the gate) and would be warped into a
single card, betrayed only by a wild border ratio, if the window count didn't
overrule it too. Only the high side is evidence — a low count proves nothing
(overlap can hide windows), so a near-miss that *fails* the count stays flagged
for review rather than being forced through. The count lands in `report.csv`'s
`windows` column.

**Both checks are ported to `checleaner.html`** (`detectPrint()`'s `solidity`
and `countWindows()`), but not with identical numbers, because the two
implementations don't decode/downscale a JPEG the same way (`cv2.resize` with
`INTER_AREA` vs a canvas `drawImage`, even with `imageSmoothingQuality:
"high"`) and JS has no `cv2.findContours(..., RETR_EXTERNAL)` to hand it a raw
contour area — `solidity` there is `closedArea / hullArea`, where `closedArea`
reuses `countWindows()`'s own hole-fill (paper pixels plus every enclosed
hole) to approximate what an external contour would enclose. On a full sweep
of `chekis/main/`, JS's window counts run a bit lower than Python's for the
same photos, so `MULTI_WINDOWS` is calibrated separately for JS (**6**, not
7) against JS's own worst-genuine-single measurement, not copied from
Python's. One real single card was found where JS's mask has a genuine small
gap Python's doesn't (bright marker writing near the border), dropping its
solidity to ~0.56 and demoting it to a flagged near-miss instead of an
auto-crop — accepted as the safe failure direction (a flag costs a look;
a wrongly-accepted grid costs a mangled photo), not chased further.

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

The **levelling, best-fit crop, and margin recentre** in this section are all
ported to `checleaner.html` (`alignMulti()` + `paperCenter()`, same tilt maths,
`CROP_ASPECTS` list, and footprint check). The **content reorientation** half
below is desktop-only — it needs a face model the offline single-file app
can't ship — so the phone app instead offers manual ⟲/⟳/180° rotate buttons to
stand a levelled result upright by hand. One consequence: `checleaner.html`
picks the `CROP_ASPECTS` shape for the frame *as levelled*, not the final
orientation, since it doesn't know the eventual turn in advance the way
`checleaner.py` does — tapping a rotate button afterward can turn a 4:3 result
into 3:4 (or the reverse), which is the user's own choice made with the image
in front of them, not a misclassification.

**Rotation.** `detect_all_prints()` runs the same paper-frame segmentation as
single-print detection, but keeps every large blob instead of just the biggest.
A rectangle looks the same every 90°, so tilt is folded into [-45°, 45°) before
combining — two prints at +44° and −44° are 2° apart, not 88°, and averaging the
raw angles would get that wrong. The frame is rotated by the **area-weighted
circular mean** of the tilts, so as many prints as possible land parallel to the
frame edges.

Those tilts come from the **photo windows**, not the blob rectangles, whenever
at least `MIN_TILT_WINDOWS` of them are rectangular enough to trust
(`_window_tilts`). A window is a print's own picture area, so its rectangle is
the *card's* rectangle. A merged blob's rectangle is not: on a staggered pile it
describes the arrangement's outline, which is tilted even when every card in it
is level — one photo's blob read −2.13° while all eight of its windows agreed on
−0.27°, and the frame came out visibly askew. A sheen bridged onto the blob skews
it further. Windows sit inside the cards, out of reach of both. The blob
rectangles remain the fallback for piles whose windows are too few or too ragged
(bright print content merges a window into the border).

**Crop.** After rotating (with the canvas expanded so nothing is clipped),
take the union bounding box of every detected blob in the rotated frame and
crop around it centred at the bounding box's own centre — centring there
makes the equal-margin requirement (top gap = bottom gap, left gap = right
gap) automatic for *any* crop size, not something to solve for separately.

One wrinkle: the detection blob can overshoot the prints at one edge. The
segmentation *close* that bridges each print's photo window (§ 3) will also
bridge a print to a patch of bright desk glare or a shadow just past it, and
that phantom extent slides the bounding box — and so the crop — off the prints,
leaving one margin at zero while the opposite one grows (a real, visible
complaint on roughly one aligned photo in five). The same close can also *clip*
a card's outer border, and then the blob's rect cuts a whole print row off the
crop. So the crop's centre **and size** both come from `_paper_bbox()`: the
actual paper, bright-and-near-neutral, **opened but not closed**, since the
close is exactly what overshot. It is trusted only when that span tracks the
blob's (not much smaller — missed prints; not much larger — grabbed a wall or
blown desk); otherwise the blob bbox stands.

Where it looks matters in both directions, and both failure modes are real.
Searching the whole rotated frame pulls in distant bright patches, over-growing
the crop until it no longer fits and alignment declines outright; searching only
inside the blob can't recover a border the segmentation clipped, so a card row
stays cut off. It searches the blob's bbox plus a `PAPER_HALO` (20%) margin, and
keeps only paper components that reach into the blob's own footprint.

It does **not** trim by edge coverage. A trim like that used to live here, to
shave a sheen fringe hugging one side, but it cannot tell that fringe from the
leading corner of a *tilted* card, whose coverage ramps up just as gently — 1%
rising to 5% over 164 columns on one photo, off which it cut 656 px of a real
print. Sheen is removed from the blob itself instead (§ 3), by how crisply each
piece of paper ends, which a tilted corner passes however thin it is.

The extent it measures comes from each blob's **outline**, not its `minAreaRect`
corners: that rectangle is itself rotated, so on a tilted pile its corners bound
far more than the prints — one 3583 × 2698 frame produced a corner box of
x[−17, 3512] y[−475, 3179], and the crop built on it cut a print in half.
Together these dropped the worst top-vs-bottom margin gap across `chekis/main/`
from 69 px to 6, and stopped a nine-print pile losing its top row.

Finally, `CROP_MARGIN` (4%) adds a little breathing room so prints aren't jammed
against the crop edge. It is applied **after** the aspect is chosen and only if
the grown crop still fits: growing before choosing would let a frame-filling
pile pick a worse-fitting shape merely because the better one no longer fit with
margin added, and a pile with no desk to spare keeps its tight crop rather than
being pushed into declining.

The crop's shape comes from `CROP_ASPECTS` (4:3, 3:4, 1:1, 16:9 — a plain
list, extend it there). For each candidate, the tightest crop at that ratio
containing every print pins one axis (zero margin) and leaves the excess on
the other, so "best fit" — horizontal and vertical margins as close as
possible — reduces to the candidate closest to the prints' own bounding-box
shape. The crop is never grown past tightest to force the margins equal:
that buys symmetry with desk. A candidate that would poke outside the photo
is disqualified; if all four are, the frame's own ratio is the fallback (the
pre-`CROP_ASPECTS` behaviour), so nothing ever cuts a print off. The choice
is recorded in `report.csv`'s `align_crop` column. 9:16 is deliberately not
in the list — an ultra-tall crop of prints on a desk reads as an accident —
which is also why the content turn (below) is folded *into* the alignment
warp rather than applied after: turning a finished 16:9 crop would flip it
into exactly that excluded shape.

**Nudge before bailing out.** The crop must stay inside the photo's real
(unrotated) footprint, checked by mapping its corners back through the inverse
rotation. But a crop whose *size* fits can still sit over one edge — one real
photo missed by 14 px of 4080, another by 1 px — and declining there throws away
a good crop over an offset, so `place()` shifts it back inside instead.

**How far it may shift is exactly its own slack**, `hw - bw2` on each axis: the
margin the crop has beyond the prints. Inside that a print can never leave the
crop; outside it one always does. That is the whole question, so it is the cap —
not a percentage. A crop pinned tight on an axis has zero slack there and cannot
move along it at all, plus the same `pad` of leeway the frame test already allows,
so a fractional tilt costing a pixel or two at the corners doesn't sink it.

An arbitrary cap was tried first (2% of the crop) and is wrong in both
directions: too loose and a crop far wider than the pile "fits" slid hard against
one edge, dumping all the desk on one side (one photo came out 298 px lopsided);
too tight and photos that could be placed safely declined instead. Worse, a cap
unrelated to slack lets the crop slide *past* the prints — three photos came back
with a whole row cut off. Candidates are also scored on how far they had to
slide, so a shape that sits centred beats one that only works jammed against an
edge.

**Do not shrink to fit.** A fallback that retried the target a few percent
smaller looks tempting for a frame-filling pile, on the theory that it eats the
leftover sheen. It eats prints: the crop must *contain* them, so shrinking below
their own extent can do nothing else, and three photos came back with a row
missing. A photo left whole is a far better outcome than one with a row cut off.

**Bail out if even that can't place it.** If no candidate and not the fallback
ratio can be placed inside the footprint, `align_multi()` returns `None` and the
photo is left whole — today's existing behaviour. This matters: these photos are
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

Geometry gives level; it can't give up. So `content_rotation()` reads the
content to choose the remaining quarter or half turn, which is decided *before*
alignment and folded into `align_multi()`'s warp (so the `CROP_ASPECTS` shape is
picked for the final orientation — see the crop paragraph in § 6); when alignment
declines, the whole frame is turned instead. It reads the **uncorrected** frame:
the face model wants a naturally exposed photo, and balancing the whites to 238.8
first costs it detections — one frame scored 2 faces at 1.81 raw but only 1 at
0.64 corrected, and turned the wrong way as a result. Across every
multi-print photo in the library the two inputs agree on all but that one, and
every file with a known correct orientation agrees on both, so this only adds.
Chekis are photographs of people, so the signal is faces: score
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
