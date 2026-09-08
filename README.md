# deltaskin-animator

Adds pressed-button animations to [Delta](https://github.com/rileytestut/Delta)
controller skins that don't have them.

Delta 2.0 supports *animated* controller skins
([commit 3e651d9](https://github.com/rileytestut/Delta/commit/3e651d9), July 2026): a
button you're holding sinks into the screen, and a d-pad tilts towards the direction
you're pressing. It's a small thing that makes a skin feel a lot less like a picture
of a controller. But a skin only gets it if the artist built it in, and most skins
predate the feature.

This tool retrofits it. Point it at a `.deltaskin` and it works out where each
button's artwork is, cuts it out, and writes a new skin with the animation wired up.
Your original file is not touched.

```
python3 animate.py "My Skin.deltaskin"
```

The rebuilt skin keeps the original's name and identifier, so importing it into Delta
**replaces** the skin you already have rather than adding a second copy with the same
name. At rest it is pixel-for-pixel identical to the skin you started with.

`--glow` adds a second kind of feedback: a soft halo that blooms well beyond the button
you're holding, so a press registers in peripheral vision without looking at your
thumb. It rides on a DeltaCore feature nothing in Delta exposes, and the build is
renamed so it installs *alongside* a plain one instead of replacing it. It goes on the
controls you use without looking — the d-pad, the face buttons and the shoulders — and
not on menu, select or save state.

```
python3 animate.py "My Skin.deltaskin" --glow
```

## Requirements

Python 3.8+ and [Pillow](https://pillow.readthedocs.io/). No other dependencies.

```
pip install -r requirements.txt
```

## Usage

Animate one skin, or a whole folder of them:

```
python3 animate.py "My Skin.deltaskin"
python3 animate.py ~/Downloads/skins -o animated
```

Rebuilt skins land in `./animated` by default (`-o` to change it). Each one prints
what it found:

```
  iphone/edgeToEdge/portrait  1290x2796
     + a       frame 172x172  art 166x167  asset 274x278  moves 1.40pt (70%)  [detected, band 5.50pt, damped 20%]
     + dpad    frame 380x380  art 374x374  asset 462x462  moves 2.43pt (81%)  [detected, band 4.50pt]
     - touchscreen        touchScreen
     - fastForward        too large
```

`moves` is how far the artwork's edge actually travels when pressed, and what
fraction that is of what a hand-built animated skin gets. `-q` prints only the
totals.

### The glow

```
python3 animate.py "My Skin.deltaskin" --glow                     # animation and glow
python3 animate.py "My Skin.deltaskin" --glow --no-animate        # glow only
python3 animate.py "My Skin.deltaskin" --glow --glow-points 8     # a tighter halo
python3 animate.py "My Skin.deltaskin" --glow --glow-color amber  # for a pale shell
python3 animate.py "My Skin.deltaskin" --glow --glow-inputs all   # menus glow too
```

| Option | Default | What it does |
| --- | --- | --- |
| `--glow` | off | Add the halo. |
| `--glow-points N` | `36` | How far past the artwork's edge it reaches, in points. |
| `--glow-color C` | `white` | What it's made of: a CSS colour name, `amber`, or `#rrggbb`. |
| `--glow-opacity N` | `1.0` | How strong it gets at its brightest, `0`–`1`. |
| `--glow-share N` | `1` | Most halos allowed to light together. `1` — the default — keeps every press to its own button. |
| `--glow-inputs LIST` | `play` | Which buttons glow: `play` for the d-pad, face and shoulder buttons, `all` for every button, or a comma-separated list of Delta input names. |
| `--no-animate` | off | Skip the press animation and only add the glow. |
| `--tag TEXT` | `GLOW` | The tag appended to the skin's name and identifier. |

`play` is the default because a halo is for the buttons you press without looking.
Start, select, menu and save state are pressed deliberately, with your eye already on
them, and lighting them isn't free: every region that goes live has to find every halo
dark, so a button glowing for no reason takes reach away from the ones beside it that
need it.

A glow build is renamed — `My Skin [GLOW]`, identifier `…​.glow` — so Delta treats it
as a separate skin and you can keep both installed and switch between them. `--tag`
changes the word if you'd rather it said something else.

White works on any shell dark enough to show it, which is most of them. On a pale
shell there is nothing for it to contrast against — a lit button and the plastic
around it are both near white — and no amount of reach or opacity fixes that. That's
what `--glow-color` is for; `amber` is the colour a light actually looks like.

Each representation reports what its halos settled on:

```
     glow 36.0pt around 8 items, 33 mask companions  (no glow: start, quickSave, menu)
     ~ dpad               keeps 82% of its glow -- even ring 14.7pt, bloom hemmed in on some sides
     ~ b                  reaches 6.3pt, not 36.0pt -- as far as it can without lighting a neighbour
     ~ a                  reaches 6.3pt, not 36.0pt -- a neighbour's glow leaves it no room at all
     ~ r                  lights with 1 other halo, all of them whole
```

`--glow-points` is what a halo asks for, not a promise. The pressed image holds every
halo at once and the mask only reveals the part of it under the button you're
touching, so a press must not reach as far as a neighbour's glow — or it would show
that glow, sliced off at a hard line. Two buttons therefore split the gap between them
half each rather than the reach going to whichever was measured first, and each takes
the longest reach that still comes out *even all the way round*: an even 10.7pt halo
looks better than a lopsided 36pt one. The gap is measured on the artwork itself, not
its bounding box, so four round buttons in a diamond get the room that's really
between them; once everything is placed each halo grows back into whatever the others
left over.

That half-gap split is the ceiling for anything in a cluster, so a default of 36pt is
not the size a face button comes out at — it's the size the ones with room come out at.
On the seven skins these were built for, 17 of 73 halos take the full 36pt, the rest
land on a median of 10.7pt, and the ones that visibly bloom are the d-pads and the
shoulder buttons, which have a corner of the shell to themselves. Raising
`--glow-points` further changes only those; a tighter number is what shrinks a
cluster.

Buttons the eye reads as a set come out **matching**, because a diamond of four whose
halos differ by a couple of points looks like a mistake even where each one is
individually as big as it could be. Same size, same kind of edge and close enough to be
seen together makes a cluster, joined neighbour by neighbour so a diamond holds together
even though its two diagonal corners are far apart. A cluster starts from the reach its
tightest member can manage and grows in lockstep — a step is taken for all of them or
none — so the whole set lands on one number. On the NDS diamond the four gaps aren't
equal (43, 43, 43 and 48 pixels), and without this the odd one out would simply have
kept its extra.

The halo starts at the button's *visible* edge, which on softly shaded art is not where
the button's flat face ends: the finder works inside the rim, and that rim can be 13
pixels of a 190-pixel button. A halo grown from the face would spend its whole reach
climbing back over the rim and never leave the button — which is exactly how a set of
NDS skins came out looking unlit. So the silhouette is grown out to the visible edge
first, as far as the touch frame allows, and `--glow-points` then means what it says.
Rims are paid for out of reach, since the gap between two buttons is the gap between
their visible edges.

What a halo does *not* have to keep clear of is a neighbour's touch frame, even
though those frames go live without it. A companion is inert — no inputs, no image —
so it's free to cover ground belonging to somebody else, and each one is sized to
swallow its partner's frame whole. The frame's rim then lies inside the mask a press
builds, where nothing can show along it. And a round button's halo isn't a rectangle at
all: DeltaCore can be asked for a disc instead, so a diamond of four face buttons
splits the whole gap between them rather than losing it to corners that hold no glow.

Two kinds of thing are in a halo's way, and they are not handled the same. A
neighbouring halo is a *hard* keep-out: a press reveals a hard-edged mask, so the two
must not touch at all, and that's what the half-gap split above is for. A button that
stays on show with no glow of its own — start, select, save state — and **the display's
own outer edge** are *soft*: nothing is sliced there, it's just somewhere a light
shouldn't wash over. A halo therefore doesn't stop dead at those; it fades out over the
last few points before it, so a shoulder button's bloom can reach out over the save and
load buttons beside it and still leave the screen edge clean.

Where a halo has something in the way it keeps its reach on the sides that are clear
and fades before the sides that aren't, which is what `keeps 54%` means. An
`even ring 14.7pt` note says it still has an unbroken ring of that width around the
artwork itself, so the button reads as lit all the way round and only the wider bloom is
one-sided. Every halo on these seven skins comes out with a full even ring; the shoulder
buttons keep 50–54% of their bloom, all of it lost to the display edge they sit under.
The two lines worth a look are a low `keeps` percentage with *no* ring, and
`no room for a glow at all -- left unlit`.

`--glow-share` above `1` trades that locality for reach: halos that would clip each
other are grouped, and pressing any one of them reveals the whole group, every halo
whole and at full reach — because a mask is a *union*, and a halo lying wholly inside
it can't be cut. The cost is that neighbours light together, so it's off by default.

Then check the result:

```
python3 verify.py animated/"My Skin.deltaskin"
```

This composites every overlay at rest and confirms it reproduces the base image
exactly — which catches any error in the crop, the declared asset size, or the
centring. On a glow build it also confirms the pressed image is nothing but the glow's
own colour blended over the base, that every halo appears exactly when its own button
is touched, that no mask edge cuts through a halo anywhere, and — by building the mask
DeltaCore really would for a touch on each button in turn — that a press leaves every
*other* button dark. Add `--original` to also confirm the name, identifier and every
touch target came through unchanged:

```
python3 verify.py animated/"My Skin.deltaskin" --original "My Skin.deltaskin"
```

To see what a press will look like without installing anything, `--render` writes
before/after close-ups (`renders/` by default):

```
python3 verify.py animated/"My Skin.deltaskin" --render          # every button
python3 verify.py animated/"My Skin.deltaskin" --render dpad a   # just these
python3 verify.py animated/"My Skin.deltaskin" --overview        # whole view
```

`press.py` reproduces DeltaCore's transform exactly, so these renders are what the
device will do, not an approximation.

## Which buttons get animated

Every button with artwork the tool can find. Some items are skipped because there is
nothing there to animate:

- **Touchscreens and thumbsticks** — Delta animates thumbsticks itself.
- **Combo zones** — the diagonal region where two d-pad inputs overlap has no
  artwork of its own.
- **Full-screen gesture areas** — an invisible `fastForward` covering a third of the
  view isn't a button.
- **Items sitting on an emulator screen.**
- **Items sharing artwork.** If two items resolve to the same art, only one can
  animate it. A d-pad wins, since its tilt is the whole point; otherwise the item
  whose frame sits inside the other's gives way.

If a button's artwork can't be made out at all, the tool animates the shape of its
touch frame instead — a circle if the frame is square, a capsule if it's long — so
the button still responds. That's the fallback, not the normal path, and it shows up
as `frame shape` in the output.

## How it works

The hard part isn't the animation, it's that **the base image still has the button
painted into it.**

Hand-built animated skins cut each button out of the layered source art, so the base
image has a hole where the button was and the separate button image fills it. We only
have the flattened PNG. We can't punch a hole in it, because Delta's skin picker
renders the base image on its own — a hole would show up in the thumbnail.

So each overlay is cut from the flattened image and left sitting exactly where it came
from. At rest it's an identical copy of what's underneath, so it's invisible. When
pressed it shrinks — and uncovers the original button's edge, still painted in the
base image underneath. A ghost outline.

The fix is to carry a band of surrounding background along with the button, wide
enough to cover the edge it moved away from. That band is the whole difficulty:

- **Too narrow** and the old edge shows through.
- **Too wide** and it drags neighbouring artwork along — the dish ring around a
  d-pad warping with the press, the bezel beyond a button's plate clipping over it.
- **Also too wide** and the animation gets weaker, not just uglier. Delta centres the
  overlay on the item's frame and scales it about that centre, so a larger overlay
  means the artwork inside it moves proportionally less. Every pixel of band costs
  responsiveness.

So the band is grown outward from the artwork through smooth background only, stopping
dead at any edge that isn't the button's own (a geodesic dilation — it can't step over
a fence). Then the width is *measured* rather than guessed: each candidate overlay is
run through the real transform in all nine press states, and the narrowest band whose
pressed footprint still covers the artwork's resting footprint wins. Coverage is
judged on both leaked area and gap thickness, because a hairline where a button
touches something else is invisible while a thin ring all the way around is exactly
the ghost we're avoiding.

Where a button is fenced in so tightly that even the widest band can't cover it, the
asset box is padded symmetrically instead. That damps the movement — less travel, but
no ghost. Buttons tangent to the edge of the plate they sit on usually end up here.

`skinlib.py` finds the artwork, `press.py` is DeltaCore's transform, `animate.py`
chooses each band and writes the skins, `verify.py` checks them.

## How the glow works

DeltaCore has been able to draw a pressed state for years and nothing in Delta's
interface exposes it. Alongside a skin's image it looks for a second file with
`_pressed` inserted before the extension, and blends that over the normal one through
a mask built from **the frame of every item currently being touched**. So a pressed
image whose only difference is a halo around each button gives exactly the effect
wanted, and the artwork at rest is untouched — the skin picker's thumbnail, which
draws the base image alone, doesn't change at all.

The mask is the catch. It's hard-edged, so a halo that hasn't faded to nothing before
the edge of the region showing it shows up on screen as a bright patch with a straight
side — and the frames in these skins hug their artwork, 172×172 around 166×167 of
button. There's about a third of a point of room, nowhere near enough for a glow you'd
notice out of the corner of your eye.

Widening the buttons' own frames is the obvious move and it's wrong. A button's frame
is inert for input, but a d-pad's four directional zones are measured from its frame:
the boundary between "up" and "nothing" sits at `frame.minY + frame.height / 3`.
Widen a d-pad's frame by *n* and that boundary moves out by *n*/3 — the dead patch in
the middle grows — and because it depends on the frame alone, no compensating
`extendedEdges` can put it back. On a control whose responsiveness is the whole point,
that isn't a trade worth making.

So **no existing item is modified.** Each one instead gains a *companion*: an extra
entry in `items` with empty `inputs`, no artwork, and a frame big enough for the halo.
Empty inputs make it completely inert — it fires nothing, and with no asset DeltaCore
never gives it an image view. Its only effect is to put a larger rectangle into the
mask, and its `extendedEdges` are picked so its extended frame is exactly its
partner's, which is what makes the halo appear precisely when that button is touched
and not a moment sooner. Companions go one per halo an item lights, so an `a+b` corner
gets two of them and the mask ends up the union of two button-sized rectangles rather
than one big one spanning both.

### A round button gets a round region

A halo is round and a rectangle is not, so the corners of a rectangular region hold no
glow at all while reaching furthest towards a diagonal neighbour — and reaching into a
neighbour is exactly what costs that neighbour its own reach. On the NDS skins the four
face buttons sit in a diamond 45 pixels apart, and a square frame's corner comes within
5 of the next button's artwork, so every halo on that diamond had to die inside 5 pixels.

There is a second shape to be had. Alongside a frame, an item may carry `"mask":
"circle"`, and DeltaCore then adds the *disc* inscribed in that frame instead of the
frame itself — a radial gradient, white out to a radius of half the frame's width and
clear a pixel past it. Nothing about input changes: the touch target is the extended
frame either way, so a disc costs the button nothing at all.

So a round button whose artwork fills its frame out to the rim asks for a disc, and
gets a single companion that is one circle wide enough to swallow the whole halo. There
is nothing outside the artwork for a corner to expose, and the two buttons split the
real gap between them. Anywhere a disc isn't right — a wide flat pill, where a radius
of half the width would bulge out above and below the button — the frame stays a
rectangle, and the companion is instead two overlapping rectangles with the corners cut
away as deep as the glow inside them allows. They overlap, so the lines where they meet
lie inside the union and are never a mask edge; the diagonal neighbour gets its room
back for nothing.

The halo around a round button is drawn round to the pixel, which takes a second bit of
care. A halo is a distance field — how far each pixel is from the silhouette — and in
general that's built by growing the silhouette one ring at a time, each ring a discrete
approximation of a circle. Over twenty rings the approximation drifts a couple of pixels
out of round, and on a twenty-pixel halo that is plainly lopsided. Where the silhouette
*is* a circle there's nothing to approximate — the distance to it is arithmetic — so
those rings are drawn as circles outright and the aura comes out exact.

The fade across it is slightly concave rather than linear, for the same reason the reach
is worth fighting for: how far a halo may go is set by its neighbours, so the reach is a
fixed budget, and a fade that has dropped below what a screen can show halfway out has
spent the second half of that budget on nothing. Staying bright almost to the end and
then dropping is what a crowded cluster can afford, and it's worth about a tenth of the
visible aura.

A disc is worth having in the other direction too, on the items that have no glow of
their own: a combo zone, a touchscreen, a button `--glow-inputs` left out, or a d-pad,
whose own glow lives outside its frame by construction. Their frames put nothing on
show but liability — whatever their corners happen to lie over — so the smaller of the
two shapes is strictly better. An N64's C-pad is a single 395-unit square with five
other buttons packed against its corners, and shrinking it to a disc is the difference
between four of that skin's halos coming out lopsided and one.

### D-pads glow in the direction you're pushing

A d-pad is one item firing four inputs, so a companion pinned to it would light the
whole halo whichever way your thumb went — a cross glowing evenly all round, saying
nothing. Worse, the glow over its own face hides the arrows and the tilt, which is the
feedback that was already there.

The directional zones are the way in. DeltaCore picks a d-pad's input from where inside
it the touch landed: the "up" zone is the top third of the frame plus the extended
margin above it, and each zone already includes the margins on its own outer sides. So
a companion whose *extended* frame is exactly one of those zones lights precisely while
that direction is held — the only handle the mask gives on which way a cross is being
pushed.

That means the halo has to be cut into four pieces, and every cut line is a mask edge
some press leaves exposed. Two things follow. The glow stays entirely **outside** the
frame, because the frame itself is in the mask for any touch anywhere on the d-pad, so
anything inside it lights in every direction at once. And what's left is shaped into a
**plus** — four arms straight out of the frame's sides, each narrowing to nothing before
it reaches the arm's full width — so the corners, where all four cut lines cross, hold
nothing to cut. The arms reach back a few pixels inside the frame as well: two
rectangles that merely abut share a line that lies on the outside of neither, and
overlapping puts the join properly inside the union.

An arm is a **wedge**, not a stub: it tapers along its length and across its width at
once, drawn as several dozen nested shapes plus a profile that rises over the artwork's
inset, because a shape that merely narrows at the tip still meets the cut lines square
where it leaves the frame. And because a wedge only occupies the middle of the side it
grows from, arms are allowed a little further out than the reach asked for — a cross's
glow is all bloom, and a short arm reads as no feedback at all. That bonus is still
bounded by the arm's half of the gap to the next artwork; without it, the GBA's d-pad
reached 9px into L and L answered by leaving a 31px slice of its own face unlit while
held. Each arm's *rectangle* is then pulled in to the glow actually inside it, since a
piece spanning a whole frame edge is mostly empty and every empty pixel of it is
somewhere a neighbour's glow has to be dark for nothing. That was a dark 13px band
across the bottom of the N64's A button.

The cost is that a d-pad only has the strip between its frame and its neighbours to
glow in. That's usually plenty — these frames sit a few units off the arm tips — but on
a skin where every side of it belongs to somebody else, the strip can be taken
completely, and the halo is reported as `left unlit`.

What's left is a packing problem, because the pressed image holds every halo at once:
any region that goes live reveals whatever falls inside it, cut off at its edge. A press
has to light its own button and nothing else, so no region may reach as far as a
neighbour's glow.

A neighbour's *frame* is a different matter, and this is the part that makes complete
rings possible. A companion fires nothing and draws nothing, so it's free to cover
ground belonging to somebody else — including half of an unpressed button. Each one is
sized to swallow its partner's frame whole, which puts that frame's rim inside the
union a press builds, where nothing can show along it. So a halo never has to die
before a neighbour's frame; only before the neighbour's glow. And where a frame can't
be swallowed, it can often be shrunk to the disc inside it instead, which is what makes
a diamond of four buttons come out with four whole halos.

Two lines are neither a neighbour's glow nor a rim that can be swallowed. A button left
out of `--glow-inputs` stays on show with nothing lit behind it, and the **display
rectangle** is the screen the game is drawn into — a halo washing over its edge puts a
bright seam along the picture. Neither can slice anything, since neither has a glow to
be cut, so a halo doesn't stop at them: it keeps its reach and *fades out* over the last
few points before crossing, and the widest even ring that clears them is put back
underneath. That is the whole reason the shoulder buttons on these skins bloom out over
the save and load buttons beside them while the screen edge above stays clean, and it's
why they report `keeps 50–54%` — the missing half is bloom that would have landed on the
display.

Which leaves the gap between two pieces of artwork, split half each — the only split
that doesn't depend on which was measured first. Each halo takes the longest reach that
fits in its half and stays dark along every rectangle it isn't shown inside, and comes
out even all the way round; an even short halo looks better than a long one with a bite
out of it. Bounding boxes are a blunt instrument for measuring that gap, since four
round buttons in a diamond have boxes overlapping at the corners while the buttons are
half an inch apart, so the silhouette itself is grown a pixel at a time until it touches
something. Then, once every halo is placed, they take turns growing a step further into
whatever is really free, each step kept only while every mask it touches stays dark
along its edges. On the SNES that pass is worth 9pt → 10.7pt on the face diamond and
27pt → the full 36pt on the d-pad.

A cluster grows as one unit through all of that: the step is drawn for the whole set and
kept only if every member can hold it, so the four buttons of a diamond can't drift apart
in the scramble for leftovers. A last pass levels any cluster that did drift anyway, down
to its smallest member — which is not quite free, since levelling down brings a smaller
region with it and a neighbour's glow that was buried inside the old wider one can end up
crossing the rim of the new one. So the whole field is measured again afterwards, and a
cluster that can't be levelled without a seam keeps the mismatch, which is the lesser
fault.

There is an arithmetic ceiling to all of this that no amount of care gets past. A round
button's companion is one circle of its own radius plus the aura, and that circle already
contains the button's frame, so what two neighbours may have between them is the distance
between their centres less one button's width — 235 pixels less 190 on the DSXL diamond,
about 22 each. Measured they get 8, the rest going on the rim the silhouette has to be
grown out through first. Shrinking the frames would buy nothing, since the companion
swallowed them anyway. This is why `--glow-points 36` lands as 8.3pt on that diamond and
the full 36 on a d-pad with a corner of the shell to itself: the number is a ceiling, and
what a crowded cluster gets is set by its neighbours' centres and its own bevel.

Some lines can't be dodged at all. A d-pad's companions are its arms, and an arm runs
from the frame's edge straight outward across whatever is beside it — on the N64, the
shoulder buttons sitting directly above the C cluster — so pushing the cluster one way
puts a line across a shoulder button's glow whatever that button does. But there's no
glow behind those lines to be spoiled, so a halo that can't fit inside them keeps its
reach and fades out *before*
crossing one instead: whichever side of the line holds less of the halo is taken away
over a ramp finishing well short of it, so there's nothing along it to make a step. Then
the widest ring that *does* fit on every side is put back underneath, so the button
still reads as lit all the way round and only the bloom beyond it is one-sided. Such a
halo still keeps to its half of the gap — its companion is as big as its reach, and a
halo let off the split because it was going to be lopsided anyway would take its
neighbour's ring away as well as its own.

`--glow-share` above `1` opts out of all of this. The mask is a *union*, so a halo lying
wholly inside it is never cut — only one crossing the union's boundary is. So halos that
would clip each other can be **grouped**, and a press on any of them puts the whole
group's regions into the mask: every one comes out whole, at full reach, with nothing
faded and nothing shortened. The cost is that they light together, which is the one
thing a press shouldn't do, hence the default of `1`. Groups join transitively, so the
number caps how big one may get, and group membership isn't quite enough to decide what
a press reveals: a combo item like `a+b` lights only two of a group of four, so the
reveal set is closed over the group of *every* halo the touch lights, or the other two
get sliced off inside the two that were revealed.

One thing a fade like that can spoil is the button's own face. A neighbour's region can
cross the artwork itself, and a ramp there dims part of the button while you're
holding it, which reads as the button lighting unevenly — worse than a glow that simply
doesn't reach. So a halo in that position drops the wash over its own face and keeps
to a rim, unless the clipping has taken so much of the rim that the wash is all it has.

Trimming is still there for what none of that fixes, and the tool measures the brightest
the glow gets along the parts of the mask that really are on the outside of the union,
pulling in whichever halo is responsible until nothing shows. `glow.py` is all of
this, and its module docstring goes into more detail.

## Limitations

- Tuned for skins drawn as **flat or softly shaded shapes with a defined rim** — the
  neumorphic and photorealistic styles most Delta skins use. Heavily textured
  backgrounds (carbon weave, camo) read as edges and can fence a band in early,
  which shows up as damping.
- A skin whose representations point at **different base images per orientation** has
  its overlays cut from the first one. Check the output for a `!` warning.
- Only the flattened image is available, so a button that visually overlaps another
  can't be fully separated from it.
- **Buttons close together get shorter halos than `--glow-points` asks for**, because
  a press may not reach as far as its neighbour's glow and an even halo is worth more
  than a long one. If everything on a skin reports
  `as far as it can without lighting a neighbour` at a fraction of what you asked for,
  the artwork is packed that tightly and raising
  `--glow-points` won't change it — two round neighbours can have the distance between
  their centres less one button's width between them, and no more. `--glow-share 6` will,
  at the price of neighbouring buttons lighting along with the one you pressed.
- On a skin packed tightly enough that a neighbour's region runs across a button's own
  artwork, that button glows as a rim rather than a lit face, and where the rim alone
  isn't enough it keeps a wash that shades off towards the neighbour. Watch for a low
  `keeps` percentage with no `even ring`.
- A **d-pad glows outside its own frame only**, so its feedback is a bloom past the arm
  you pushed rather than a lit cross — anything inside the frame would light in all four
  directions at once. Same for a C-pad whose buttons sit deep inside one big frame: its
  halo has nowhere to go and comes out faint. The N64's is the worst case in these seven
  skins — four small buttons inside a 411-unit square, inset 78–84 units from its sides,
  which is further than the whole reach — so it glows above and below in portrait and
  keeps only 7% in landscape, one faint nub over the top C button. The press animation
  itself is unaffected; it's only the glow that can't get out.
- A **thick rim** is paid for twice: the silhouette is grown out through it, and the
  gap that bounds the reach shrinks by the rim on both buttons. A pair of buttons with
  wide bevels and little space between them ends up with a short halo whatever
  `--glow-points` says.
- A **pale shell** gives white nothing to contrast against. Reach and opacity don't
  help; `--glow-color amber` does.
- A d-pad hemmed in on all four sides can lose its glow entirely, since it only has the
  strip outside its own frame to work with.
- The glow is baked into the `_pressed` image, so `--glow-color`, `--glow-points` and
  `--glow-opacity` are build-time choices, not something you can change on the device.
- Nothing here needs a device, but nothing here has been tested on every skin in the
  wild either. Run `verify.py` and look at a couple of `--render` close-ups before
  trusting a rebuild.

## Credits

Delta and DeltaCore are by [Riley Testut](https://github.com/rileytestut); animated
controller skin support and the `_pressed` image the glow rides on are both his, and
this tool just fills in the assets his format already expects. The skins you point it at belong to whoever drew them — this
repository ships no skin artwork, and please don't redistribute a rebuilt skin without
the artist's blessing.

## License

MIT — see [LICENSE](LICENSE).
