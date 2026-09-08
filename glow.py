#!/usr/bin/env python3
"""A soft glow that blooms around a button while it is held down.

DeltaCore has been able to do this for years and nothing in Delta's interface
exposes it. Alongside the skin's image, `ControllerSkin.image(for:assetSize:
isPressed:)` looks for a second file with `_pressed` inserted before the
extension, and `ButtonsInputView` blends that image over the normal one through
an alpha mask built from *the frame of every item currently being touched*. So a
pressed image whose only difference from the base is a halo around each button
gives exactly the effect wanted, and the artwork at rest is untouched -- the skin
picker's thumbnail, which draws the base image alone, doesn't change at all.

The mask is the catch, and it shapes everything here.

It is hard-edged, so a halo that hasn't faded to nothing before the mask's edge
appears on screen as a bright patch with a straight side. And the region an item
puts into it is its own frame, which DeltaCore adds for whatever is being touched,
so the halo has to die inside that frame. The frames in these skins hug their
artwork -- 172x172 around 166x167 of button -- which leaves about a third of a
point of room, nowhere near enough for a glow you could see out of the corner of
your eye.

Widening the buttons' own frames is the obvious move and it is wrong. A button's
frame is inert for input (`.standard` inputs fire anywhere in `extendedFrame`, so
compensating `extendedEdges` holds the touch target exactly), but a d-pad's four
directional zones are measured from its *frame*: `ButtonsInputView.inputs(at:)`
puts the boundary between "up" and "nothing" at `frame.minY + frame.height / 3`.
Widen a d-pad's frame by n and that boundary moves outward by n/3 -- the neutral
patch in the middle grows -- and because the boundary depends on the frame alone,
no choice of `extendedEdges` can put it back. On a control whose responsiveness
is the whole point, that is not a trade worth making.

So no existing item is modified. Each item that can light something up instead
gains a *companion*: an extra entry in `items` carrying

    "inputs": [], "frame": <big enough for the halo>, "extendedEdges": <mirror()>

An empty `inputs` array parses as `.standard([])`, which makes the companion
completely inert -- it contributes no inputs, and with no `asset` it never gets
an image view, so `activate/deactivateControllerSkinItems` skip over it. Its only
effect is to put a large enough rectangle into the mask. Its `extendedEdges` are
picked so its `extendedFrame` is exactly its partner's, which is what makes the
glow appear precisely when that item is touched and not a moment sooner.

Companions go one per halo an item can light, not one per item, so the `a+b`
square between two buttons gets two of them -- pressing it presses both buttons,
so both should light -- and the mask ends up the *union* of two button-sized
rectangles rather than the one big rectangle spanning them, which would have
swallowed a third button sitting in the corner between them.

There is a second shape available, and on a skin of round buttons it is most of
the answer. An item whose entry says `"mask": "circle"` contributes the disc
inscribed in its frame instead of the frame: a radial gradient centred on it with
radius half the frame's *width*, white to the radius and clear a pixel later. A
square frame's corners reach a root two further than the round artwork inside it,
and the frame is always in the mask, so on the DS diamond -- buttons 45 pixels
apart -- the corner of one frame lands 5 pixels from the next button's artwork.
Every halo in the cluster then has to be dark 5 pixels out, which is no halo at
all. A disc leaves nothing sticking out past the artwork and the two buttons split
the whole 45 between them. `mask` is read in exactly one place, the pressed
image's blend, so nothing about a touch target changes; `mask_box` is where the two
shapes are told apart, and `rim` and `boundary` are where a region's own shape
decides which pixels count as its edge.

A disc is offered wherever it really does stand in for the frame. On a round button
that means a square frame the artwork fills out to the rim, and then the halo's
companion is a single disc as well -- `spanning` sizes it to the glow it has to
hold, the tightest mask a round halo can have. Everywhere else a frame is worth
shrinking for the opposite reason: an item with no halo of its own, and a d-pad,
whose bloom lives outside its frame in arms, have nothing inside their frames to
uncover, so those corners are pure liability -- all they can do is light whatever
they happen to lie over. An N64's C-pad is one 395-unit square with five other
buttons packed against its corners.

Where a halo isn't round, its companion is two overlapping rectangles rather than
one (`plus`), with a square taken out of each corner of the box. The halo is round
where its box is not, so those corners hold no glow while reaching furthest towards
a diagonal neighbour -- and what a companion reaches over is exactly what its
neighbours lose. The cut is the deepest that leaves both the corner squares
themselves and the union's boundary dark. Because the two pieces overlap, the lines
where they meet lie inside the union and are never measured as an edge.

What is left is a packing problem, and one thing decides its shape: a press must
light the button under your thumb and nothing else. The pressed image holds every
halo at once, so any region that goes live reveals whatever falls inside it --
including a neighbour's glow, cut off at the region's edge.

The way out is that a companion is free to cover ground that isn't its own. It
fires nothing and draws nothing; all it does is put a rectangle in the mask, and
the rectangle may lie over half of an unpressed neighbour without lighting so much
as a pixel of it. So each companion is sized to swallow its partner's *frame*
whole, which puts that frame's rim inside the union where nothing can show along
it. A halo therefore never has to die before a neighbour's frame. It only has to
die before the neighbour's *glow* -- and where two halos would meet, `spread`
gives each one half the gap between the two silhouettes, the only split that
doesn't come down to which was measured first.

Where the halo begins is the other half of it. `skinlib` finds a button by flooding
the flat shape inside its rim, so on softly shaded art the silhouette stops a bevel
short of what the eye calls the button's edge -- 13 pixels of a 190-pixel button on
the DS. A halo grown from there climbs back over the bevel and never leaves the
button, which is how the DS skins came out looking unlit. So each silhouette is first
grown out to the visible edge (`visible`), as far as its own touch frame allows, and the
reach is counted from there. Rims cost reach: the gap two buttons split is the gap
between their visible edges.

Measuring that gap in bounding boxes gets it badly wrong in exactly the
arrangement these skins like most: four round buttons in a diamond have boxes that
overlap at the corners while the buttons are half an inch apart. So `crowd` dilates
the silhouette itself a pixel at a time and sees what it really touches, and once
every halo is placed, `expand` lets them take turns growing a step further into
whatever the pixels say is still free.

Halos may be grouped instead, and then they do come out at full reach whatever the
spacing: a mask is a *union*, so a halo lying wholly inside it is never cut, and a
press that emits companions for two halos shows both of them whole. The price is
that they light together, which is the one thing this is supposed to avoid, so
`GLOW_SHARE` is 1 and no group is ever formed unless it is raised. With it raised,
groups join transitively and `shown` closes the reveal set over the group of every
halo a position lights -- a combo item (`a+b`) lights two of a group of four, and
the other two would be cut inside the two that were revealed.

Some lines can't be dodged at all. A d-pad's companions are its arms, and an arm
runs from the frame's edge outward across whatever is beside it -- on the N64, the
shoulder buttons sitting directly above the C cluster. Nothing is behind those lines
to be spoiled, though -- they belong to items with no halo of their own, or to the
wrong side of one -- so a halo that can't fit inside them may keep its reach and
fade out *before* it crosses one (`clip`): whichever side of the line holds less of the halo is taken away over a
ramp finishing well short of it, so there is nothing along it to make a step. The
widest ring that does fit on every side then goes back underneath, so the button
reads as lit all the way round and only the bloom past it is one-sided.

A halo in that position keeps to its half of the gap all the same. Its companion is
as big as its reach, and a peer has to be dark before that companion's rim, so a
halo let off the split on the grounds that it was going to be lopsided anyway takes
its neighbour's ring away as well as its own -- and the clipping spreads across the
cluster. What it may do instead is pick the reach that survives the clipping best:
the fade is a fraction of the reach, so past a point asking for more glow leaves
less of it standing.

What such a fade can spoil is the button's own face, since the rectangle it is
dodging may cross the artwork itself; a dimmed patch on a button you are holding
reads as the button lighting unevenly, which is worse than a glow that doesn't
reach. So a halo in that position keeps to a rim and drops the wash over its face,
unless the clipping has taken so much of the rim that the wash is all it has.

Trimming is still there for what clipping can't fix (a keep-out too narrow to
fade inside), and a halo that would leave a seam even then is dropped. `build`
measures the brightest the glow gets along the parts of the mask that really are
on the outside of the union, and pulls in whichever halo is responsible. The glow
fills the room it has.
"""

import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# Set GLOW_DEBUG to have the packing explain itself: the room each halo starts
# with, what stands in the way of the ones that can't be even, and any that get
# dropped. Which halo lost what to whom is otherwise very hard to see from the
# outside, since every reach depends on all the others.
DEBUG = bool(os.environ.get('GLOW_DEBUG'))

GLOW_POINTS = 36.0       # how far past the artwork's edge the halo reaches

# Which inputs are worth a halo. The point of the glow is a press you catch out of
# the corner of your eye while looking at the game, which is what the controls you
# play with are: the d-pad, the face buttons, the shoulders. Menu, save state, load
# state and fast forward are pressed deliberately, with your eye on them, so a glow
# there is light where nothing is happening -- and it isn't free, because every
# frame that goes live has to find every halo dark, so a button that glows for no
# reason takes reach away from the ones next to it that need it.
GLOW_INPUTS = frozenset({'up', 'down', 'left', 'right',
                         'a', 'b', 'x', 'y', 'z',
                         'l', 'r', 'l2', 'r2', 'l3', 'r3',
                         'cUp', 'cDown', 'cLeft', 'cRight'})
GLOW_COLOR = (255, 255, 255)   # what the glow is made of; white unless asked
GLOW_OPACITY = 1.0       # the colour at its strongest, just outside the artwork
FACE_FRACTION = 0.7      # ... and over the button's own face, relative to that
FALLOFF = 0.85           # fade exponent: 1 is linear, lower stays bright further out
CROSS_REACH = 1.6        # a d-pad's reach, relative: it only glows outside itself
CROSS_FADE = 0.9         # of that reach spent narrowing each arm to nothing
CROSS_SEAM = 3           # px an arm reaches back into the frame, to bury the join
CROSS_STEPS = 48         # levels an arm's wedge fades over: see `arms`
BLUR_FRACTION = 0.3      # of the reach spent on a closing blur, not on rings
MIN_POINTS = 2.5         # a halo shorter than this isn't worth the file size
GLOW_SHARE = 1           # most halos allowed to light together; 1 keeps them apart
CLIP_FADE = 0.7         # of the reach spent dying out before a foreign frame

# ... but never more than this many points of it. The fade is what keeps a halo off
# a line it isn't allowed to cross, and how long it has to be is a property of the
# line, not of the reach: a ramp this wide is already smooth enough that nothing
# shows along it. Left proportional, a long reach paid for itself twice over -- the
# fade grew with it and ate what it had just bought, so asking for more glow left
# less of it standing, and the crowded skins were exactly where that bit hardest.
CLIP_REACH = 4.0

# How much of the halo a foreign frame's edge may cut through, out of 255. The
# mask shows the pressed image inside that rectangle and not outside it, so
# whatever the halo is worth along that line is a step on screen; a couple of
# levels of white is below anything a display will show.
EDGE_TOLERANCE = 6

# Below this fraction of the glow it started with, a halo counts as gone: the
# clipping took all of it, and what is left isn't worth a companion.
EMPTY_SHARE = 0.02

# A lopsided halo gets an even ring underneath, out to whatever does
# fit, so the light is unbroken where it is brightest -- at the button's own edge
# -- and only the bloom past it is one-sided. Rings shorter than this are too thin
# to read as a ring at all, and a halo that can't have one goes without.
RING_POINTS = 1.25

# Most of the shorter side of a touch frame that the silhouette may be grown by to
# reach the button's visible edge; see `visible`. A frame that is much larger than
# the artwork it belongs to is a frame with shell in it, and the glow has no
# business starting out there.
RIM_SHARE = 0.15

# When a clipped halo does without the wash over the button's own face. It keeps
# the wash while at least `FACE_KEEP` of the washed halo survives the clipping --
# the bite is off in a corner and nobody will see it -- and gives it up below that,
# but only while at least `FACE_DROP` of the rim is left to carry the press on its
# own. Where the clipping takes the rim as well, the wash is all the button has,
# and a patchy lit face beats a press with nothing to show for it.
FACE_KEEP = 0.8
FACE_DROP = 0.5

# Reaches to try, as fractions of the one asked for, when something is in the way.
TRIMS = (1.0, 0.85, 0.72, 0.6, 0.5, 0.42, 0.34, 0.28, 0.23, 0.18)

ROUNDS = 4               # relaxation passes; one halo shrinking can free another

ROUND = 'circle'         # DeltaCore's name for a disc-shaped mask
ROUND_SLACK = 2          # px a disc may miss the shape it is standing in for


def shifted(mask, dx, dy):
    """`mask` moved by whole pixels, with black shifted in behind it."""
    moved = Image.new('L', mask.size, 0)
    moved.paste(mask, (dx, dy))
    return moved


def swell(mask, steps, phase=0):
    """`mask` grown `steps` pixels outwards, as round as a pixel grid allows.

    A square dilation -- `MaxFilter(3)`, four of them for four pixels of reach --
    travels 1.41 pixels diagonally for every one it travels straight, so a round
    button comes out of it a rounded square, with its corners pointing at whatever
    sits diagonally away. Alternating a square step with a diamond one (the four
    neighbours, no corners) gives an octagon instead, within 4% of a circle, and
    the same in every direction.

    `phase` continues an alternation already in progress, so a field built one step
    at a time comes out the same shape as one built in a single call."""
    for step in range(steps):
        if (step + phase) % 2:
            mask = mask.filter(ImageFilter.MaxFilter(3))
        else:
            # All four shifts come off the same starting mask. Chaining them
            # instead lets right-then-down compose into a diagonal, which is a
            # square step wearing a diamond's clothes -- and the whole alternation
            # collapses back to 1.41 diagonal pixels per straight one.
            grown = mask
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                grown = ImageChops.lighter(grown, shifted(mask, dx, dy))
            mask = grown
    return mask


def depths(art, reach):
    """How far each pixel lies outside the `art` silhouette, in rounded steps: 1
    just outside it, `reach` at the far edge, and 0 both on the artwork itself and
    beyond `reach`.

    Every halo is a level table away from this (`halo`), and the search asks for
    the same silhouette at a dozen different reaches, so the shape is worked out
    once here and the reaches cost nothing after that."""
    dist = Image.new('L', art.size, 0)
    grown = art
    for step in range(1, min(reach, 255) + 1):
        previous, grown = grown, swell(grown, 1, phase=step - 1)
        dist.paste(step, (0, 0), ImageChops.subtract(grown, previous))
    return dist


def radial(size, circle, rings):
    """The same distance field as `depths`, for a circle, worked out exactly.

    `depths` grows the silhouette one step at a time, and a step is a discrete
    approximation of a circle: over twenty of them the error accumulates into an
    aura a couple of pixels out of round, which on a twenty-pixel halo is enough
    for the eye to call it lopsided. Where the silhouette *is* a circle there is
    nothing to approximate -- the distance to it is arithmetic -- so the rings are
    drawn as circles, outermost first, and the halo comes out perfectly round.

    `circle` is `(centre x, centre y, radius)` in the field's own coordinates."""
    field = Image.new('L', size, 0)
    draw = ImageDraw.Draw(field)
    for step in range(rings, -1, -1):
        edge = circle[2] + step
        draw.ellipse((circle[0] - edge, circle[1] - edge,
                      circle[0] + edge, circle[1] + edge), fill=step)
    return field


def halo(art, reach, face=FACE_FRACTION, dist=None):
    """A soft falloff reaching `reach` pixels beyond the `art` silhouette.

    Rings of decreasing strength one step apart, then a blur, which smooths the
    step between one ring and the next. The brightest point is the artwork's own
    edge; the face gets a gentler lift so the button reads as lit rather than
    washed out.

    The fade is slightly concave (`FALLOFF` below 1) because how far a halo may
    reach is set by its neighbours, not by how bright it is: a reach is a fixed
    budget, and a fade that has dropped below what a screen can show halfway
    through has spent the second half of that budget on nothing. Staying bright
    almost to the end and then dropping is what a crowded cluster can afford.

    `face` is that lift, and a d-pad passes 0: its arrows and the tilt it does
    when pressed are the feedback, and white over them erases both.

    `dist` is a `depths` field already built for this silhouette, of at least this many
    rings; without one it is built here."""
    rings = max(1, round(reach * (1.0 - BLUR_FRACTION)))
    sigma = max(0.6, (reach - rings) / 3.0)
    if dist is None:
        dist = depths(art, rings)

    alpha = dist.point([0] + [round(255 * (1.0 - (step - 0.5) / rings) ** FALLOFF)
                              if step <= rings else 0 for step in range(1, 256)])
    if face:
        alpha.paste(round(255 * face), (0, 0), art)
    return alpha.filter(ImageFilter.GaussianBlur(sigma))


def visible(mask, box, frame, cap):
    """The silhouette grown out to the button's visible edge, to start a halo from.
    `box` and `frame` are in `mask`'s own coordinates.

    `skinlib` finds a button by flooding the flat shape inside its rim, so on
    softly shaded art the silhouette stops a bevel short of the edge the eye sees
    -- 13 pixels of a 190-pixel button on the DS. A halo grown from there spends
    its whole reach climbing back over the bevel and never leaves the button.

    Growing the silhouette itself doesn't fix it: the bevel is thicker on some
    sides than others, and the aura comes out that much thicker with it. The touch
    frame is the shape to grow to. It hugs the artwork on these skins, and being a
    rectangle centred on the button it is symmetric by construction -- which is
    what the eye compares the aura against.

    How round it should be comes from the artwork: the fraction of its own box the
    silhouette fills says whether it is a circle (0.79), a pill, or a rectangle
    (1.0), and one corner radius follows from all three. Artwork sitting further
    than `cap` inside its frame is not a button hugged by its frame -- the frame
    has shell in it, and the glow has no business starting out there -- so that
    one is left as it is.

    Returns the silhouette and, where the shape it grew to is a circle, that circle
    -- which is what lets the halo around it be drawn exactly round; see `radial`."""
    if any(inset > cap for inset in (box[0] - frame[0], box[1] - frame[1],
                                     frame[2] - box[2], frame[3] - box[3])):
        return mask, None
    filled = sum(count for level, count in enumerate(mask.histogram())
                 if level > EDGE_TOLERANCE)
    wide, high = frame[2] - frame[0], frame[3] - frame[1]
    ratio = filled / max(1.0, (box[2] - box[0]) * (box[3] - box[1]))
    radius = min(min(wide, high) / 2.0,
                 math.sqrt(max(0.0, 1.0 - ratio) * wide * high / (4.0 - math.pi)))
    grown = mask.copy()
    ImageDraw.Draw(grown).rounded_rectangle(
        (frame[0], frame[1], frame[2] - 1, frame[3] - 1),
        radius=round(radius), fill=255)
    circle = None
    if abs(wide - high) <= 2 * ROUND_SLACK and 2 * round(radius) >= min(wide, high):
        # The corner radius reached its cap, so what was drawn is the circle
        # inscribed in the frame -- in the coordinates `rounded_rectangle` used.
        circle = ((frame[0] + frame[2] - 1) / 2.0, (frame[1] + frame[3] - 1) / 2.0,
                  (min(wide, high) - 1) / 2.0)
    return grown, circle


def solid(size, box, offset):
    """A filled stencil of a region, in a halo's own coordinates."""
    stencil = Image.new('L', size, 0)
    shape = (box[0] - offset[0], box[1] - offset[1],
             box[2] - offset[0] - 1, box[3] - offset[1] - 1)
    draw = ImageDraw.Draw(stencil)
    if is_round(box):
        draw.ellipse(shape, fill=255)
    else:
        draw.rectangle(shape, fill=255)
    return stencil


def encloses(mask, offset, box, slack=0):
    """Whether `mask`, grown by `slack`, covers every pixel of the region `box`."""
    if slack:
        mask = swell(mask, slack)
    return ImageChops.subtract(solid(mask.size, box, offset), mask).getbbox() is None


def spanning(alpha, offset, centre):
    """The smallest radius about `centre` that holds every lit pixel of `alpha`."""
    span = alpha.getbbox()
    if span is None:
        return 0.0
    worst = 0.0
    for y in range(span[1], span[3]):
        row = alpha.crop((span[0], y, span[2], y + 1)).getbbox()
        if row is None:
            continue
        away = y + offset[1] - centre[1]
        for x in (span[0] + row[0], span[0] + row[2] - 1):
            worst = max(worst, math.hypot(x + offset[0] - centre[0], away))
    return worst


def mass(alpha):
    """How much glow there is in an image, in arbitrary units."""
    return sum(level * count for level, count in enumerate(alpha.histogram()))


def profile(length, start, stop, fade):
    """A 0-255 weight along one axis: nothing outside `start`..`stop`, full in the
    middle, and a linear rise over `fade` at each end."""
    fade = max(1, int(round(fade)))
    levels = []
    for position in range(length):
        near = min(position - start, stop - 1 - position)
        levels.append(0 if near < 0 else
                      255 if near >= fade else round(255 * near / fade))
    return levels


def mouth(art, frame, side):
    """Where an arm reaches the edge of `frame` on one side, as the span it covers
    along that edge and how far short of the edge the artwork stops.

    Measured from the artwork rather than taken from the frame, because a frame is
    square and an arm is not: the N64's cross fills a third of the width of its
    frame, the SNES's caps a third of their dish. The span is read from the slice of
    artwork nearest the edge -- for a dish that is the little of it that comes
    closest, which is the part of it the direction is about."""
    outer = 0 if side in ('up', 'down') else 1      # the axis the arm spans
    whole = art.getbbox()
    if whole is None:
        return frame[outer], frame[outer + 2], 0
    inset = max(0, whole[1] - frame[1] if side == 'up' else
                frame[3] - whole[3] if side == 'down' else
                whole[0] - frame[0] if side == 'left' else frame[2] - whole[2])
    depth = inset + CROSS_SEAM
    strip = ((0, 0, art.width, frame[1] + depth) if side == 'up' else
             (0, frame[3] - depth, art.width, art.height) if side == 'down' else
             (0, 0, frame[0] + depth, art.height) if side == 'left' else
             (frame[2] - depth, 0, art.width, art.height))
    strip = (max(0, strip[0]), max(0, strip[1]),
             min(art.width, strip[2]), min(art.height, strip[3]))
    found = None if strip[2] <= strip[0] or strip[3] <= strip[1] \
        else art.crop(strip).getbbox()
    if found is None:
        return frame[outer], frame[outer + 2], inset
    return (max(frame[outer], strip[outer] + found[outer]),
            min(frame[outer + 2], strip[outer] + found[outer + 2]), inset)


def arms(alpha, frame, fade, mouths):
    """`alpha` confined to the four arms reaching straight out of `frame`, each
    spreading sideways as it goes and narrowing to nothing over `fade` at the edges.

    A d-pad's halo has to be handed out one direction at a time, and the only way
    to do that is to cut it into pieces the mask can turn on separately -- so every
    cut line is an edge some press leaves exposed. The lines all run out of the
    frame's corners, which is why there is nothing in the corners to cut: an arm is
    dark by the frame's edge at the latest, so two arms meeting at a corner are
    both dark there. What is left is a plus, dark along every line the cutting can
    follow, and pointing the way the thumb is pushing rather than glowing all round.

    The frame's own edge is a cut line too, and the one an arm cannot help crossing:
    the glow starts at the artwork and the artwork is right there. So an arm is a
    wedge rather than a band -- no wider than the mouth the artwork makes in that
    edge (`mouth`), opening out to `fade` either side of it on the way out. A band's
    full width at the crossing is what drew a straight bright line along the frame's
    top edge on every d-pad, out across open shell the arm had nothing to hide it on.

    Where the artwork stops short of the edge, the arm also rises from nothing over
    that gap, so the line itself stays dark: what the eye then sees is the glow
    sitting off the button's own rim, a little way inside the frame, rather than a
    bright edge with a straight side. The d-pad dishes are inset a good 13px; a cross
    whose arms reach past its frame has no gap and needs no fade."""
    weight = Image.new('L', alpha.size, 0)
    width, height = alpha.size
    for side, (near, far, inset) in mouths.items():
        outer = 0 if side in ('up', 'down') else 1
        edge = (frame[1] if side == 'up' else frame[3] if side == 'down' else
                frame[0] if side == 'left' else frame[2])
        away = -1 if side in ('up', 'left') else 1
        end = (-1 if away < 0 else (height if outer == 0 else width))
        arm = Image.new('L', alpha.size, 0)
        draw = ImageDraw.Draw(arm)
        for step in reversed(range(CROSS_STEPS)):
            share = step / (CROSS_STEPS - 1)
            spread = round(fade * share)
            out, back = max(frame[outer], near - spread), \
                min(frame[outer + 2], far + spread)
            slant, level = edge + away * max(1, round(fade)), round(255 * (1 - share))
            points = [(near, edge), (far, edge), (back, slant),
                      (back, end), (out, end), (out, slant)]
            draw.polygon(points if outer == 0
                         else [(y, x) for x, y in points], fill=level)
        span = (0, edge) if away < 0 else (edge, height if outer == 0 else width)
        rise = Image.new('L', (1, height) if outer == 0 else (width, 1))
        rise.putdata(profile(height if outer == 0 else width,
                             span[0], span[1], inset))
        weight = ImageChops.lighter(weight, ImageChops.multiply(
            arm, rise.resize(alpha.size, Image.NEAREST)))
    return ImageChops.multiply(alpha, weight)


def rim(size, box, offset):
    """A one-pixel stencil of a region's edge, in a halo's own coordinates."""
    stencil = Image.new('L', size, 0)
    shape = (box[0] - offset[0], box[1] - offset[1],
             box[2] - offset[0] - 1, box[3] - offset[1] - 1)
    draw = ImageDraw.Draw(stencil)
    if is_round(box):
        draw.ellipse(shape, outline=255, width=1)
    else:
        draw.rectangle(shape, outline=255, width=1)
    return stencil


def along(alpha, offset, boxes):
    """The brightest the halo gets along the edge of any of those rectangles --
    what each would show as a step if it went live while this halo was drawn."""
    return max([0] + [ImageChops.darker(alpha, rim(alpha.size, box, offset)
                                        ).getextrema()[1] for box in boxes])


def plus(box, cut):
    """`box` with a square `cut` taken out of each corner, as two overlapping
    rectangles.

    A halo is round and its box is not, so the corners of the box hold nothing --
    and they are what reaches furthest towards a button sitting diagonally away,
    where its own artwork can end up inside them. Handing the mask two rectangles
    instead of one keeps the same glow and gives the diagonal neighbour its room
    back. They overlap, so the lines where they meet lie inside the union."""
    return [(box[0], box[1] + cut, box[2], box[3] - cut),
            (box[0] + cut, box[1], box[2] - cut, box[3])]


def ladder(top, bottom):
    """Reaches from `top` down to `bottom`, each a fifth shorter than the last."""
    reach, seen = float(top), set()
    while reach >= bottom:
        if round(reach) not in seen:
            seen.add(round(reach))
            yield round(reach)
        reach *= 0.8


def clearance(a, b):
    """How far apart two rectangles are, never claiming more than the truth: the
    larger of their separations along the two axes, and zero if they touch. The
    real distance between two corners is longer, which is the safe way to be
    wrong."""
    return max(0, a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3])


def clip(alpha, offset, keepouts, fade):
    """`alpha` faded to nothing before it crosses the edge of any of `keepouts`.

    Every region that belongs to something else -- its frame, and the companions
    lighting its glow -- puts this halo on screen, cut off along its edge,
    whenever that something else is touched. On the crowded skins those regions
    overlap the artwork itself, so no amount of pulling a halo in can get out of
    the way; see the module docstring.

    Whichever side of the edge has less of the halo on it goes, over a ramp that
    finishes a good `fade` short of the edge itself, so there is nothing along the
    line to make a step and what is left fades out smoothly -- a light that just
    doesn't reach that way."""
    grow = max(2, int(round(fade)))
    room = None
    for box in keepouts:
        local = (box[0] - offset[0], box[1] - offset[1],
                 box[2] - offset[0], box[3] - offset[1])
        if intersect(local, (0, 0, alpha.width, alpha.height)) is None:
            continue
        edge = (local[0], local[1], local[2] - 1, local[3] - 1)

        if along(alpha, offset, [box]) <= EDGE_TOLERANCE:
            continue                    # the halo is already nothing on that line

        inside = mass(alpha.crop(local))                 # which side has less to lose
        outward = mass(alpha) - inside > inside
        inner = (edge[0] + grow, edge[1] + grow, edge[2] - grow, edge[3] - grow)
        if not outward and (inner[2] <= inner[0] or inner[3] <= inner[1]):
            continue                    # too small to fade inside; leave it to the trim

        patch = Image.new('L', alpha.size, 0 if outward else 255)
        draw = ImageDraw.Draw(patch)
        if outward:
            draw.rectangle((edge[0] - grow, edge[1] - grow,
                            edge[2] + grow, edge[3] + grow), fill=255)
        else:
            draw.rectangle(inner, fill=0)
        patch = ImageChops.invert(patch.filter(ImageFilter.GaussianBlur(grow / 3.0)))
        room = patch if room is None else ImageChops.darker(room, patch)

    return alpha if room is None else ImageChops.multiply(alpha, room)


# --- rectangles -------------------------------------------------------------
# Frames live in the skin's mapping units and images in pixels, which are the
# same thing in every skin seen so far but needn't be, so the two are kept apart.

def intersect(a, b):
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[2] > box[0] and box[3] > box[1] else None


def union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def scaled(box, scale, outward=True):
    """`box` under a per-axis scale, rounded outwards so nothing is clipped.
    Whatever shape the box carries (see `round_box`) comes with it."""
    grow, shrink = (math.floor, math.ceil) if outward else (math.ceil, math.floor)
    return (int(grow(box[0] * scale[0])), int(grow(box[1] * scale[1])),
            int(shrink(box[2] * scale[0])), int(shrink(box[3] * scale[1]))) + box[4:]


def round_box(centre, radius):
    """The square `radius` around `centre`, marked as a disc.

    A region is a box, and a box with `ROUND` on the end of it is the disc
    inscribed in that box: DeltaCore's `mask: circle`, a radial gradient centred on
    the frame with radius half its *width*, white to the radius and clear a pixel
    later. `intersect`, `union` and `scaled` go on treating it as the box it sits
    in, which is the right answer for all three -- only the rim of it is a
    different shape, and that lives in `rim` and `boundary`."""
    return (round(centre[0] - radius), round(centre[1] - radius),
            round(centre[0] + radius), round(centre[1] + radius), ROUND)


def is_round(box):
    return len(box) > 4 and box[4] == ROUND


def mirror(frame, extended):
    """`extendedEdges` that give a companion with `frame` the partner's
    `extendedFrame`. DeltaCore reads them as an outset -- `origin -= left`,
    `width += left + right` -- and a companion's frame is the larger of the two,
    so these come out negative, which is legal and nowhere clamped."""
    return {'top': frame[1] - extended[1], 'bottom': extended[3] - frame[3],
            'left': frame[0] - extended[0], 'right': extended[2] - frame[2]}


# --- items ------------------------------------------------------------------

def input_names(item):
    """Every input an item can fire, as a set of names."""
    inputs = item['inputs']
    return set(inputs) if isinstance(inputs, list) else set(inputs.values())


def worth_glowing(item, allowed=GLOW_INPUTS):
    """Whether an item is one of the controls a halo is for; see `GLOW_INPUTS`.
    `allowed` of `None` means every item that has artwork."""
    return allowed is None or bool(input_names(item) & set(allowed))


def directional(item):
    """Whether an item is a d-pad: four inputs picked by where inside it the
    touch landed. Thumbsticks are directional too but DeltaCore drives them
    itself, and they never reach here."""
    inputs = item['inputs']
    return (isinstance(inputs, dict) and 'thumbstick' not in item
            and {'up', 'down', 'left', 'right'} <= set(inputs))


def edges_of(item, rep):
    """An item's `extendedEdges` after the representation's defaults are merged
    in, the way `ControllerSkin.Item.init` merges them: per side, not wholesale."""
    merged = dict.fromkeys(('top', 'bottom', 'left', 'right'), 0)
    for source in (rep.get('extendedEdges') or {}, item.get('extendedEdges') or {}):
        for side, value in source.items():
            if side in merged:
                merged[side] = value
    return merged


def frame_box(item):
    frame = item['frame']
    return (frame['x'], frame['y'],
            frame['x'] + frame['width'], frame['y'] + frame['height'])


def disc_in(box):
    """The disc DeltaCore draws for `mask: circle` on a frame: centred on it, with
    radius half its *width*, whatever its height."""
    return round_box(((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0),
                     (box[2] - box[0]) / 2.0)


def mask_box(item):
    """What an item puts into the pressed image's mask when it is touched: its
    frame, or the disc inside that frame if the item asked for `mask: circle`."""
    box = frame_box(item)
    return disc_in(box) if item.get('mask') == ROUND else box


def extended_box(item, rep):
    box, edges = frame_box(item), edges_of(item, rep)
    return (box[0] - edges['left'], box[1] - edges['top'],
            box[2] + edges['right'], box[3] + edges['bottom'])


def zones(item, rep):
    """Where a touch has to land for each of a d-pad's four directions, copied
    from `ButtonsInputView.inputs(at:)`.

    Each zone runs a third of the frame in from its own side and spans the whole
    extended frame the other way, so a touch in a corner fires two directions and
    one in the middle fires none. A companion whose *extended* frame is one of
    these lights exactly while that direction is held -- which is the only handle
    the mask gives us on which way a d-pad is being pushed."""
    frame, reach = frame_box(item), extended_box(item, rep)
    third = ((frame[2] - frame[0]) / 3.0, (frame[3] - frame[1]) / 3.0)
    return {
        'up': (reach[0], reach[1], reach[2], round(frame[1] + third[1])),
        'down': (reach[0], round(frame[3] - third[1]), reach[2], reach[3]),
        'left': (reach[0], reach[1], round(frame[0] + third[0]), reach[3]),
        'right': (round(frame[2] - third[0]), reach[1], reach[2], reach[3]),
    }


def companion(frame, extended):
    """An inert item whose only job is to widen the mask. `inputs: []` parses as
    `.standard([])`: no inputs to report, and no `asset`, so no image view."""
    entry = {
        'inputs': [],
        'frame': {'x': frame[0], 'y': frame[1],
                  'width': frame[2] - frame[0], 'height': frame[3] - frame[1]},
        'extendedEdges': mirror(frame, extended),
    }
    if is_round(frame):
        entry['mask'] = ROUND
    return entry


# --- mask regions -----------------------------------------------------------

def boundary(box, others):
    """A stencil over `box` marking the parts of its rim that lie on the outside
    of the union of all of them.

    A rim buried in a sibling is not a boundary and nothing shows along it, which
    is the whole reason companions are handed out one per halo: an item's own
    frame sits inside the companion covering its glow, and two companions side by
    side hide each other's facing edges. Siblings are erased a pixel shy of their
    own rims, so a rim two regions share stays a boundary in both."""
    stencil = Image.new('L', (max(1, box[2] - box[0]), max(1, box[3] - box[1])), 0)
    draw = ImageDraw.Draw(stencil)
    edge = (0, 0, stencil.width - 1, stencil.height - 1)
    if is_round(box):
        draw.ellipse(edge, outline=255, width=1)
    else:
        draw.rectangle(edge, outline=255, width=1)
    for other in others:
        inner = (other[0] - box[0] + 1, other[1] - box[1] + 1,
                 other[2] - box[0] - 2, other[3] - box[1] - 2)
        if inner[2] < inner[0] or inner[3] < inner[1]:
            continue
        if is_round(other):
            draw.ellipse(inner, fill=0)
        else:
            draw.rectangle(inner, fill=0)
    return stencil


def field_over(halos, box):
    """Every halo, as one image, over just the rectangle `box`."""
    patch = Image.new('L', (max(1, box[2] - box[0]), max(1, box[3] - box[1])), 0)
    for entry in halos.values():
        if intersect(box, entry['box']) is None:
            continue
        paste_lighter(patch, entry['alpha'], (entry['offset'][0] - box[0],
                                              entry['offset'][1] - box[1]))
    return patch


def steps(halos, regions):
    """The step each of `regions` leaves along the outside of their union.

    That number is what the mask shows on screen: inside the regions the pressed
    image is drawn and outside them it is not, so whatever the glow is worth on
    the dividing line is a hard edge."""
    for index, box in enumerate(regions):
        if all(intersect(box, entry['box']) is None for entry in halos.values()):
            yield index, 0
            continue
        stencil = boundary(box, regions[:index] + regions[index + 1:])
        yield index, ImageChops.darker(field_over(halos, box),
                                       stencil).getextrema()[1]


def brightest(halos, regions):
    """The worst of those steps, giving up as soon as one is too big to accept."""
    worst = 0
    for _, found in steps(halos, regions):
        worst = max(worst, found)
        if worst > EDGE_TOLERANCE:
            break
    return worst


def build(rep, size, sources, points, ppp, report=None, sharing=GLOW_SHARE):
    """Work out every halo, and the companion items that let them be seen.

    `sources` maps an item's index to (silhouette, offset) in image pixels.
    Returns the glow laid over the whole image, the companions to append to
    `rep['items']`, and what each halo settled on.

    Every halo starts at the reach asked for and is trimmed until no mask
    rectangle in the skin cuts a visible step out of any of them. Trimming one
    halo can give another room, and shrinking a halo shrinks the rectangle around
    it, so it takes a few passes to settle; reaches only ever shrink, so it does
    settle."""
    mapping = rep['mappingSize']
    to_pixels = (size[0] / mapping['width'], size[1] / mapping['height'])
    to_units = (mapping['width'] / size[0], mapping['height'] / size[1])

    items = rep['items']
    wanted = max(1, round(points * ppp))
    floor = max(1, round(MIN_POINTS * ppp))

    frames = [scaled(frame_box(item), to_pixels) for item in items]
    names = [input_names(item) for item in items]

    # A halo reaches further out than the crop its artwork was found in has room
    # for, so each silhouette moves onto a canvas of its own -- which also keeps
    # the ring dilations off all the empty space around it. A d-pad keeps the
    # silhouette it was found with: its frame is a square around a cross, and
    # filling that square would put solid glow in the corners, where the shape of
    # the thing being pressed is.
    silhouettes, arts, circles = {}, {}, {}
    for index, (art, offset) in sources.items():
        span = art.getbbox()
        if span is None:
            continue
        box = (offset[0] + span[0], offset[1] + span[1],
               offset[0] + span[2], offset[1] + span[3])
        want = box if directional(items[index]) else union(box, frames[index])
        pad = round(wanted * max(1.0, CROSS_REACH)) + 4
        origin = (want[0] - pad, want[1] - pad)
        canvas = Image.new('L', (want[2] - want[0] + 2 * pad,
                                 want[3] - want[1] + 2 * pad))
        canvas.paste(art.crop(span), (box[0] - origin[0], box[1] - origin[1]))
        if want != box:
            canvas, circle = visible(
                canvas,
                (box[0] - origin[0], box[1] - origin[1],
                 box[2] - origin[0], box[3] - origin[1]),
                (frames[index][0] - origin[0], frames[index][1] - origin[1],
                 frames[index][2] - origin[0], frames[index][3] - origin[1]),
                round(RIM_SHARE * min(frames[index][2] - frames[index][0],
                                      frames[index][3] - frames[index][1])))
            span = canvas.getbbox()
            box = (origin[0] + span[0], origin[1] + span[1],
                   origin[0] + span[2], origin[1] + span[3])
            if circle is not None and not directional(items[index]):
                circles[index] = circle
        silhouettes[index] = (canvas, origin)
        arts[index] = box
    crosses = {index for index in silhouettes if directional(items[index])}

    # What the item's own touch frame puts into the mask. DeltaCore will draw it as
    # a disc instead of a rectangle (`mask: circle`: a radial gradient centred on
    # the frame, radius half its width, white to the radius and clear a pixel
    # later), and on a round button that one word is the whole packing problem.
    #
    # The frame of a button is a square around a circle, and its corners are what
    # ruins the crowded skins. They reach a root two further than the artwork does,
    # and the frame is always in the mask -- DeltaCore adds it for whatever is being
    # touched -- so on the DS diamond, where the buttons sit 45 pixels apart, the
    # corner of one frame comes within 5 pixels of the next button's artwork. Every
    # halo in the cluster then has to be dark 5 pixels out, which is no halo at all.
    # Asking for a disc leaves nothing sticking out past the artwork, and the two
    # buttons get to split the whole 45 between them.
    #
    # `mask` is read for one purpose and nothing else -- the pressed image's blend,
    # `ButtonsInputView.updateInputs` -- so a touch target is not affected. It is
    # only offered where the disc really does stand in for the frame: a square frame
    # (DeltaCore's radius is half the frame's *width*, so a disc on a wide flat
    # button would bulge out above and below it) which the artwork fills out to the
    # rim, leaving nothing of the background inside the disc to be lit.
    masks, discs = list(frames), set()
    for index in range(len(items)):
        frame = frames[index]
        wide, high = frame[2] - frame[0], frame[3] - frame[1]
        if abs(wide - high) > 2 * ROUND_SLACK:
            continue          # the radius is half the frame's *width*, so on a wide
                              # flat button a disc bulges out above and below it
        disc = disc_in(frame)
        if index not in silhouettes or index in crosses:
            # Nothing of this item's own glow is inside its frame: it has none at all
            # -- a combo zone, a touchscreen, a button left out of `GLOW_INPUTS` --
            # or it has arms, which live outside the frame by construction. The frame
            # is then pure liability, uncovering whatever its corners happen to lie
            # over, and a disc is the smaller of the two shapes DeltaCore offers.
            masks[index], items[index]['mask'] = disc, ROUND
        elif encloses(silhouettes[index][0], silhouettes[index][1],
                      disc, ROUND_SLACK):
            masks[index], items[index]['mask'] = disc, ROUND
            discs.add(index)

    # Buttons the eye reads as a set: the same round frame, close enough together to
    # be seen at once. Their halos have to match, because a cluster is compared with
    # itself. Nothing about the packing makes that happen on its own -- the DS
    # diamond isn't quite a diamond, and its four buttons come out of the share-out
    # with gaps of 43, 43, 43 and 48 pixels, so one of them ends up with a couple of
    # pixels more aura than the other three and the cluster looks askew. So peers are
    # held to a single reach: they start at the shortest any of them can have, and
    # from there they grow in step or not at all.
    #
    # Only the near ones, though. Two clusters at opposite corners of the shell are
    # never in the same glance, and holding them to one reach would cost the roomy
    # one its glow for the sake of a comparison nobody makes.
    def hugged(index):
        """Whether the halo starts from the frame: `visible` took this for a button
        its frame hugs and grew the silhouette out to it, so the aura is measured
        from a shape the frame decides rather than from the artwork's own outline.
        Two of those, the same size and side by side, are a set."""
        return index not in crosses and arts[index] == frames[index]

    def alike(index, other):
        return (hugged(index) and hugged(other)
                and abs((frames[index][2] - frames[index][0])
                        - (frames[other][2] - frames[other][0])) <= 2 * ROUND_SLACK
                and abs((frames[index][3] - frames[index][1])
                        - (frames[other][3] - frames[other][1])) <= 2 * ROUND_SLACK
                and clearance(arts[index], arts[other]) <= 2 * wanted)

    # Neighbour by neighbour, so a diamond holds together: its two diagonal corners
    # are further apart than a halo ever reaches, but each is beside the other two.
    peers = {index: [index] for index in silhouettes}
    for index in sorted(silhouettes):
        for other in sorted(silhouettes):
            if other > index and alike(index, other) \
                    and peers[index] is not peers[other]:
                joined = sorted(peers[index] + peers[other])
                for member in joined:
                    peers[member] = joined

    shaped, banded, crowds, fields = {}, {}, {}, {}
    mates = {}        # item -> every item whose press shows this one's halo
    seen = {}         # item -> every halo its own press shows, whole

    def distances(index):
        """This silhouette's distance field, built once at the longest reach it
        could ever be asked for. Every reach below that is a level table away.

        A round button's is arithmetic rather than grown a ring at a time, so its
        aura is a circle to the pixel; see `radial`."""
        if index not in fields:
            top = wanted * (CROSS_REACH if index in crosses else 1.0)
            rings = max(1, round(top * (1.0 - BLUR_FRACTION)))
            fields[index] = (radial(silhouettes[index][0].size, circles[index], rings)
                             if index in circles
                             else depths(silhouettes[index][0], rings))
        return fields[index]

    def shape(index, reach, face=FACE_FRACTION):
        """The halo an item wants at a given reach, before anything is taken out.

        A d-pad glows in four arms outside its frame, and nowhere else. Its own
        frame is in the mask for every touch anywhere on it, so anything inside it
        lights whichever way the thing is pushed -- the glow all around a cross
        that says nothing about the direction. What is left outside the frame gets
        handed out a direction at a time, which needs the corners empty; see
        `arms`. The frames here sit within a few units of the arm tips, so the
        bloom still starts where the artwork ends.

        Because of that the arms are grown further than the reach asked for
        (`CROSS_REACH`) -- what a cross spends climbing out of its own frame is
        reach the other buttons never pay. That bonus stops at its half of the gap
        to the next artwork all the same. An arm is worn as a rectangle the width
        of the glow inside it, so an arm grown past the halfway line puts that
        rectangle over the neighbouring button, and the neighbour's own glow has to
        be dark under it: on the GBA the d-pad's right arm reached 9px into L, and
        L answered by leaving a 31px slice of its own face unlit while held. With
        nothing within reach at all -- the SNES and DSXL d-pads have a corner of the
        shell to themselves -- there is no line to stay behind and the bonus stands
        in full."""
        art, offset = silhouettes[index]
        if index not in crosses:
            return halo(art, reach, face=face, dist=distances(index))
        near, top = crowd(index), round(reach * CROSS_REACH)
        reach = max(1, top if near is None else min(top, max(reach, near // 2)))
        alpha = halo(art, reach, face=0.0, dist=distances(index))
        local = (frames[index][0] - offset[0], frames[index][1] - offset[1],
                 frames[index][2] - offset[0], frames[index][3] - offset[1])
        ImageDraw.Draw(alpha).rectangle(
            (local[0], local[1], local[2] - 1, local[3] - 1), fill=0)
        return arms(alpha, local, reach * CROSS_FADE,
                    {side: mouth(art, local, side)
                     for side in ('up', 'down', 'left', 'right')})

    def grown(index, reach, keepouts=(), ring=0, face=FACE_FRACTION):
        """A halo, the box it occupies, and the companion region that holds it.

        The region swallows the partner's frame, which is live beside the
        companion. Frames here hug their artwork, so a frame rim left outside
        would sit in the brightest part of the glow, where no amount of trimming
        would ever get it below a step.

        `ring` is a shorter reach that fits on every side, unioned back in after
        the clipping so the glow is unbroken around the artwork itself and only the
        bloom beyond it is one-sided.

        `face` is how much of a wash the button's own face gets; see `faces`."""
        offset, asked = silhouettes[index][1], reach
        alpha = shape(index, reach, face)
        if keepouts:
            alpha = clip(alpha, offset, keepouts,
                         min(reach * CLIP_FADE, CLIP_REACH * ppp))
            if ring:
                alpha = ImageChops.lighter(alpha, shape(index, ring, face))
        span = alpha.getbbox() or (0, 0, 0, 0)
        box = (span[0] + offset[0], span[1] + offset[1],
               span[2] + offset[0], span[3] + offset[1])
        region = union(box, masks[index])
        alone = {index: {'alpha': alpha, 'offset': offset, 'box': box}}

        if index in discs:
            # One disc, as small as the glow allows: the tightest mask a round halo
            # can have, so nothing is cut and nothing of a neighbour's is shown. The
            # extra pixel is DeltaCore's own fade from white to clear.
            #
            # Centred on the button is the obvious answer and it is only right for a
            # halo that reaches the same distance all round. One that blooms into the
            # room on its left and fades out before the neighbour on its right is not
            # centred on its button, and a disc that is loses half its radius to empty
            # space on the crowded side -- reaching back over the very neighbour that
            # shortened it, and taking that neighbour's own reach away in turn. So the
            # centre of the glow is offered as well, and whichever gives the smaller
            # disc wins. Either way `spanning` measures from the centre being tried,
            # so the disc holds the whole halo and nothing is cut.
            middle = ((masks[index][0] + masks[index][2]) / 2.0,
                      (masks[index][1] + masks[index][3]) / 2.0)
            circle = min((round_box(centre,
                                    math.ceil(spanning(alpha, offset, centre)) + 1)
                          for centre in (middle, ((box[0] + box[2]) / 2.0,
                                                  (box[1] + box[3]) / 2.0))),
                         key=lambda disc: disc[2] - disc[0])
            return {'alpha': alpha, 'offset': offset, 'reach': reach, 'asked': asked,
                    'box': box, 'region': union(region, circle), 'pieces': [circle]}

        def hollow(cut):
            """Whether the corner squares `plus` takes out hold no glow.

            Two things ride on that. Nothing is missing from the mask that was worth
            drawing -- a corner cut out of a lit patch would read as a notch. And the
            item's own frame, which is live beside its companion whenever the item
            itself is touched, may stick out through the cut: the frame hugs the
            artwork, so if the corner is dark then the sliver of frame rim left on
            show out there has nothing along it either."""
            for x, y in ((region[0], region[1]), (region[2] - cut, region[1]),
                         (region[0], region[3] - cut),
                         (region[2] - cut, region[3] - cut)):
                patch = intersect((x, y, x + cut, y + cut), box)
                if patch is not None and alpha.crop(
                        (patch[0] - offset[0], patch[1] - offset[1],
                         patch[2] - offset[0], patch[3] - offset[1])
                        ).getextrema()[1] > EDGE_TOLERANCE:
                    return False
            return True

        pieces = [region]
        for cut in ladder(reach, 1):
            trial = plus(region, cut)
            if hollow(cut) and brightest(alone, trial) <= EDGE_TOLERANCE:
                pieces = trial     # the deepest cut the glow itself allows
                break
        return {'alpha': alpha, 'offset': offset, 'reach': reach, 'asked': asked,
                'box': box, 'region': region, 'pieces': pieces}

    def family(index):
        """Every item that shows this one's halo: itself, and anything it shares a
        mask with."""
        return mates.get(index, frozenset([index]))

    def shown(position):
        """Every halo a touch on this item puts on show, whole: the ones it lights,
        the ones it shares a mask with, and everything those drag in.

        A halo is safe from being cut exactly when all of it is inside the mask, so
        showing any of a group means showing the group. That is why this closes
        over `family` rather than just listing what the item's own inputs light --
        an `a+b` corner lights two of four grouped buttons, and if it stopped there
        the other two would be cut where they reach into the first two's
        rectangles."""
        if position not in seen:
            found = set(family(position))
            for index in silhouettes:
                if names[position] & names[index]:
                    found |= family(index)
            seen[position] = frozenset(found)
        return seen[position]

    def alien(index, other, own=True):
        """Whether `other`'s companion can be live while this halo is not wholly on
        show. A companion is live wherever the halo it covers is shown, so it is off
        limits here unless every touch that shows `other` shows this one too.

        `own=False` asks about presses on anything *but* `other` itself, which is
        what a d-pad's whole-halo region needs: pressed itself, a d-pad wears one arm
        rather than the region round the lot, so that region only ever reaches the
        mask if something else fires its directions -- a separate button wired to
        `up`, say. Fencing a neighbour off a rectangle nothing draws costs it glow
        for nothing."""
        return other != index and any(
            other in shown(position) and index not in shown(position)
            for position in range(len(items)) if own or position != other)

    def fenced(index, other, entry):
        """The mask rectangles `other` can put on show while `index`'s halo is not
        wholly on show -- the lines this halo has to have faded out along."""
        boxes = []
        if alien(index, other, own=other not in crosses):
            boxes += list(entry['pieces'])
        if other in crosses and alien(index, other):
            boxes += list(bands(other, entry).values())
        return boxes

    # Each halo's reach is settled before anything is measured, because a halo
    # that fits is worth more than a longer one cut to fit: a rectangle's edge
    # drawn across a glow takes a straight-sided bite out of it however gently the
    # fade is done, and that reads as the light stopping dead against nothing.
    #
    # Two things bound an even reach. A frame that isn't this button's own goes
    # live without it, so the halo has to be nothing by the time it arrives there.
    # And a neighbour's halo goes live without it too, wearing a companion that
    # covers all of that halo, so the two of them have to share the gap between
    # their artwork -- half each, the only split that doesn't come down to which
    # was measured first.
    def exposed(other):
        """Whether a press on `other` leaves the rim of its own frame out on the
        boundary of the mask, where it can cut a halo.

        Mostly it doesn't. A companion is free to cover ground that belongs to
        somebody else -- it fires nothing and draws nothing -- so `grown` sizes each
        one to swallow its partner's frame whole. The frame's rim then lies *inside*
        the union a press builds and is measured as nothing at all; the only rim on
        show is the companion's own, out past the far edge of that button's glow.
        Which is why a halo doesn't have to die before a neighbour's frame. It only
        has to die before the neighbour's *glow*, and the two of them split the gap
        between their artwork half each.

        Two kinds of item are the exception. A d-pad's companions are arms narrower
        than its frame, so the frame's long sides stay on show. And an item with no
        halo of its own -- a combo zone, a touchscreen, one whose glow was dropped --
        has no companion to swallow anything."""
        return other not in silhouettes or other in crosses

    def crowd(index):
        """How far it is from this artwork to the nearest artwork whose halo lights
        without it, in pixels, or `None` for nothing within reach.

        Bounding boxes can't answer this and get it badly wrong in the common case:
        four round buttons in a diamond have boxes that overlap at the corners while
        the buttons themselves are half an inch apart. A box says the gap is nothing,
        the halo is written off as impossible and clipped, and a button that had room
        for a full even ring ends up with a lopsided one. So grow the silhouette a
        pixel at a time and see what it really touches -- the same rounded step the
        halo itself grows by, so a gap measured here is a gap the glow can fill."""
        if index not in crowds:
            art, offset = silhouettes[index]
            others = Image.new('L', art.size, 0)
            for other in silhouettes:
                if alien(index, other):
                    piece, place = silhouettes[other]
                    others.paste(piece, (place[0] - offset[0], place[1] - offset[1]),
                                 piece)
            crowds[index] = None
            grown = art
            for reach in range(2 * wanted + 1):
                if ImageChops.multiply(grown, others).getbbox():
                    crowds[index] = reach
                    break
                grown = swell(grown, 1, phase=reach)
        return crowds[index]

    def spread(index):
        """The longest reach that still leaves the neighbouring *halos* their own
        room: half of whatever gap there is between this artwork and the nearest
        artwork whose glow lights without this one.

        Half each is the only split that doesn't come down to which halo was
        measured first, and it binds whether or not this halo ends up clipped. A
        clipped halo's companion is as big as its reach, and a peer has to be dark
        before that companion's rim -- so a halo allowed to overrun its half on the
        grounds that it was going to be lopsided anyway takes its neighbour's ring
        away as well as its own, and the clipping spreads across the cluster."""
        near = crowd(index)
        return wanted if near is None else min(wanted, near // 2)

    def clear(index):
        """How far this halo can reach before it meets a rim that goes live without
        it and has no glow of its own to protect -- a frame that stays on show, see
        `exposed`. Reported, but not a bound: see `room`."""
        art = arts[index]
        limits = [clearance(art, masks[other]) for other in range(len(items))
                  if other != index and index not in shown(other) and exposed(other)]
        return min([wanted] + limits)

    def room(index):
        """The longest even reach: as far as the neighbouring halos allow.

        Only they bound it. A frame with no glow behind it -- `save`, `load`, the
        C-pad's own outline -- has nothing there to be spoiled, so a halo meeting one
        of those fades out before the line and reaches as far as it likes on every
        other side. Shrinking the whole ring to fit inside the nearest such frame is
        what left the N64's A and B unlit: a line 12px off one flank took the glow
        off all four, and it is a line the eye can't see anyway. The shoulder buttons
        reaching out over the save and load buttons are the same thing done right,
        and this is what gives it to the face buttons too.

        A neighbouring *halo* is the opposite case, and `spread` says why: its
        companion is as big as its reach, so overrunning it takes its ring away as
        well as this one's."""
        if DEBUG:
            # `inset` is what the silhouette still has to spare inside its frame
            # after `visible`: a big number there is a halo starting well short of
            # the button's visible edge, which is how the DS came out unlit.
            print('   room', index, sorted(names[index]), 'gap', crowd(index),
                  'frames', clear(index),
                  'inset', [arts[index][0] - frames[index][0],
                            arts[index][1] - frames[index][1],
                            frames[index][2] - arts[index][2],
                            frames[index][3] - arts[index][3]])
        return spread(index)

    def bare(index, reach, face=FACE_FRACTION):
        """The halo as it wants to be, with nothing taken out of it. `face` follows
        whatever the halo will really be drawn with, so what is measured here is
        what the skin ends up carrying."""
        if ('bare', index, reach, face) not in shaped:
            entry = grown(index, reach)
            if face != FACE_FRACTION:
                entry = dict(entry, alpha=shape(index, reach, face))
            shaped[('bare', index, reach, face)] = entry
        return shaped[('bare', index, reach, face)]

    def lit(entry, box):
        """Whether a halo has anything worth showing inside `box`."""
        patch = intersect(box, entry['box'])
        if patch is None:
            return False
        offset = entry['offset']
        return entry['alpha'].crop((patch[0] - offset[0], patch[1] - offset[1],
                                    patch[2] - offset[0], patch[3] - offset[1]
                                    )).getextrema()[1] > EDGE_TOLERANCE

    def bands(index, entry):
        """A d-pad's halo cut into its four arms, one per direction. Their union is
        the whole halo -- the corners hold nothing, by construction -- so the mask a
        press builds covers what it always did, one arm at a time.

        Each arm reaches `CROSS_SEAM` back inside the frame rather than stopping
        against it. Two rectangles that merely abut share a line that lies on the
        outside of neither and gets measured as an edge in both; overlapping puts
        the join properly inside the union, and the frame has no glow in it to
        show anyway.

        Out past the frame each piece is pulled in to the arm it holds. The arm is a
        wedge as wide as the mouth the artwork makes in the frame's edge (`arms`),
        which on the N64's C-pad is a third of the frame it sits in -- so a piece
        spanning that whole edge is mostly empty, and every empty pixel of it is
        somewhere a neighbour's glow has to be dark for nothing. That is what took
        13px off the bottom of the N64's A while it was held. The pull-in is exact:
        an arm's wedge is flat zero outside itself, so the box around what the piece
        holds still holds all of it."""
        key = (index, entry['asked'], entry['box'])
        if key not in banded:
            box, frame, seam = entry['box'], frames[index], CROSS_SEAM
            pieces = {'up': (frame[0], box[1], frame[2], frame[1] + seam),
                      'down': (frame[0], frame[3] - seam, frame[2], box[3]),
                      'left': (box[0], frame[1], frame[0] + seam, frame[3]),
                      'right': (frame[2] - seam, frame[1], box[2], frame[3])}
            banded[key] = {
                side: hugging(entry, piece, side)
                for side, piece in pieces.items()
                if piece[2] > piece[0] and piece[3] > piece[1] and lit(entry, piece)}
        return banded[key]

    def hugging(entry, piece, side):
        """`piece` shrunk to the glow inside it, except along the edge that lies
        inside the frame -- the seam, which has nothing lit on it to measure and has
        to stay where it is so the arms still overlap there."""
        patch = intersect(piece, entry['box'])
        offset = entry['offset']
        found = None if patch is None else entry['alpha'].crop(
            (patch[0] - offset[0], patch[1] - offset[1],
             patch[2] - offset[0], patch[3] - offset[1])).getbbox()
        if found is None:
            return piece
        near = (patch[0] + found[0], patch[1] + found[1],
                patch[0] + found[2], patch[1] + found[3])
        return (near[0], near[1], near[2], piece[3]) if side == 'up' else \
               (near[0], piece[1], near[2], near[3]) if side == 'down' else \
               (near[0], near[1], piece[2], near[3]) if side == 'left' else \
               (piece[0], near[1], near[2], near[3])

    def cut_by(index, entry):
        """Which items would show a step in this halo if it reached this far: the
        ones whose mask rectangles have a rim running through lit glow."""
        found = set()
        for other in range(len(items)):
            if other == index or index in shown(other):
                continue
            boxes = [masks[other]]
            if other in silhouettes:
                boxes += fenced(index, other, wide[other])
            if along(entry['alpha'], entry['offset'], boxes) > EDGE_TOLERANCE:
                found.add(other)
        return found

    def share(links, limit):
        """Items grouped so that anything cutting a halo is in the halo's own
        group -- the transitive closure of `links`, since a group has to hold
        everything its members drag in.

        Which is also why it needs a limit. Groups join up: a d-pad close to a
        shoulder button, the shoulder close to `select`, `select` close to `start`,
        and one press lights the whole bottom of the skin. Past `limit` halos a
        link is refused and the two go back to keeping out of each other's way,
        which is what the trimming and fading below are for. Links are taken in
        index order, so a skin always comes out the same way."""
        groups = {index: {index} for index in range(len(items))}
        for one, two in links:
            if groups[one] is groups[two]:
                continue
            merged = groups[one] | groups[two]
            if len(merged & set(silhouettes)) > limit:
                continue
            for index in merged:
                groups[index] = merged
        return {index: frozenset(group) for index, group in groups.items()}

    # Rather than keep each halo away from everything that could cut it, let the
    # press that would cut it show the whole thing instead. A mask is a union of
    # rectangles, so a halo lying entirely inside one is never cut -- only a halo
    # crossing the union's boundary is. So whichever items would cut a halo are
    # grouped with it, and a press on any of them brings every halo in the group
    # along, complete. Nothing has to be shortened or faded, and every button gets
    # a whole ring at the reach asked for.
    #
    # The price is that a press lights its neighbours' halos as well as its own.
    # For a few buttons that close together that reads as light spilling onto the
    # plastic around them, which is what a light does, and the button that moves is
    # still the one being held -- but a whole skin lighting at once says nothing at
    # all, so `sharing` is the most halos allowed to light together. 1 keeps every
    # halo to itself, at whatever reach it can have alone.
    if sharing > 1:
        wide = {index: bare(index, wanted) for index in silhouettes}
        mates.update(share([(index, other) for index in sorted(silhouettes)
                            for other in sorted(cut_by(index, wide[index]))],
                           sharing))
        seen.clear()       # `shown` answers differently now the groups exist

    # An even halo wins however short it comes out, so long as it is a halo at all.
    # A ring all the way round at 6pt is a lit button; the same glow with a
    # straight-sided bite out of one flank is a button that looks wrong, and no reach
    # makes up for that. What it is worth shortening for is a neighbour's glow -- see
    # `room` for what it is not worth shortening for.
    #
    # `room` is where the ladder starts, not a verdict. It goes by pixels now, but the
    # closing blur carries a little past the reach it was grown to, so the ladder
    # still has the last word.
    asked = {index: max(floor, min(wanted, room(index))) for index in silhouettes}
    asked = {index: min(asked[other] for other in peers[index])
             for index in silhouettes}          # a cluster glows as one; see `peers`
    # And the ceiling for the rest of the search, `expand` included. Half the gap
    # each is a bargain between neighbours, and a bargain one of them is free to
    # break isn't one: a halo grown past its half is dark on every mask -- its
    # neighbour is too small to make a step anywhere -- so nothing downstream objects,
    # and the neighbour is left with the floor. Which is exactly what the N64's A had
    # happen to it by B.
    limit = dict(asked)
    clipped = set()

    # What a clipped halo has to stay out of, measured against what its neighbours
    # settled on. Reaches only ever shrink from here, and shrinking one only
    # shrinks the region around it, so this bound covers every configuration the
    # search can still arrive at and nothing oscillates.
    #
    # A d-pad's own companions are its arms, whose long sides run up the middle of
    # its halo rather than round the outside of it, so those count too: nothing of
    # the d-pad's own is there to be cut, but a neighbour reaching in would be.
    def fences(reaches):
        reachable = {index: bare(index, reaches[index]) for index in silhouettes}
        return {index: [piece for other in silhouettes
                        for piece in fenced(index, other, reachable[other])]
                for index in silhouettes}

    # The lines with nothing behind them: a frame that stays on show but has no glow
    # of its own, and the edge of the display. Crossing one of these spoils nothing,
    # so a halo isn't shortened for them -- it fades out before them and keeps
    # whatever it has on its other sides. They don't move as the reaches settle
    # either, which is why they are measured once and the `fences` are not.
    #
    # The display's edge is a line like any other, and the one line no mask can ever
    # put a halo the far side of. A button flush with it -- the DS shoulders sit
    # against it -- had its glow simply cut off there, which on screen is a bright
    # strip down the very edge of the phone with a straight side. Nothing is being
    # revealed or hidden, so `step` has nothing to measure and never complained; it
    # is just ugly. Faded, it reads as a light that doesn't reach the edge rather
    # than one sawn off at it.
    display = (0, 0, size[0], size[1])
    lines = {index: [display]
                    + [masks[other] for other in range(len(items))
                       if other != index and index not in shown(other)
                       and exposed(other)]
             for index in silhouettes}

    def blocks(index):
        """Everything a halo has to be dark on or fade out before."""
        return keepouts[index] + lines[index]

    # Settling the reaches moves the very rectangles they were measured against: a
    # halo that shrinks pulls its companion in with it, and a neighbour faded
    # against the old, wider rectangle is left bright on the new one's rim -- a step
    # it would be dropped for further down. So measure, settle, and measure again
    # until the fences stop moving. Reaches only ever come down within a pass, and
    # a pass can only start from where the last one finished, so this converges.
    keepouts = fences(asked)
    for _ in range(ROUNDS):
        # The geometry says an even halo fits; the pixels have the last word, since
        # the closing blur carries a little past the reach it was grown to. Step
        # down the ladder until it really is dark on every line, and give up on
        # evenness rather than on the glow.
        for index in sorted(asked):
            if index in clipped:
                continue
            for trim in TRIMS:
                reach = max(floor, round(asked[index] * trim))
                if along(bare(index, reach)['alpha'], bare(index, reach)['offset'],
                         keepouts[index]) <= EDGE_TOLERANCE:
                    asked[index] = reach
                    break
                if reach <= floor:
                    # A neighbour's glow this close leaves nothing worth drawing
                    # clear of it, so the halo takes the bite instead: a lopsided
                    # glow beats none, and it goes back up to its half of the gap.
                    # Shrinking was the wrong answer -- what is in the way runs
                    # across the artwork, so a shorter halo is just as blocked with
                    # less left over. It stops at `limit` all the same: overrunning
                    # that would take the neighbour's ring as well as its own.
                    clipped.add(index)
                    asked[index] = limit[index]
                    break

        settled = fences(asked)
        if settled == keepouts:
            break
        keepouts = settled

    # Which halos actually meet something on the way out. A halo trimmed to fit
    # between its neighbours usually still crosses a line with nothing behind it --
    # that is the whole point of not shortening for those -- so this is where the
    # clipper's work is decided, not in the ladder above.
    bitten = {index for index in sorted(silhouettes)
              if along(bare(index, asked[index])['alpha'],
                       bare(index, asked[index])['offset'],
                       blocks(index)) > EDGE_TOLERANCE}

    if DEBUG:
        for index in sorted(bitten):
            entry = bare(index, asked[index])
            for box in blocks(index):
                hit = along(entry['alpha'], entry['offset'], [box])
                if hit > EDGE_TOLERANCE:
                    print('   blocks', index, sorted(names[index]), hit, box)

    # What a bitten halo can still have all the way round. `room` won't answer this:
    # it only knows about the neighbouring halos, and most of what a halo is faded
    # against is a line it was allowed to reach past. The pixels know the difference,
    # so this ladder asks them, in finer steps than the reach search needs -- what's
    # left down here is a rim, and a rim a fifth thinner is still a rim. Every
    # rectangle the relaxation goes on to measure is one of these keep-outs or inside
    # one, so a ring dark on all of them stays dark however the rest of the skin
    # settles.
    rings = {}
    for index in sorted(bitten):
        for reach in ladder(asked[index], max(1, round(RING_POINTS * ppp))):
            entry = bare(index, reach, 0.0)
            if along(entry['alpha'], entry['offset'],
                     blocks(index)) <= EDGE_TOLERANCE:
                rings[index] = reach
                break

    # Whether a bitten halo washes over the button's own face. The rectangles it is
    # dodging belong to its neighbours and can run right across the artwork, so the
    # fade that keeps it off one of those lines dims a patch of the button while it is
    # being held -- which reads as the button lighting unevenly, and a glow that draws
    # attention to its own edges is worse than one that doesn't reach. Kept to the rim
    # instead, an obstructed glow just looks obstructed.
    #
    # That only holds while there is a rim left to carry it. Where the clipping takes
    # most of that too, the wash is all the button has, and a lopsided face is better
    # than a press with nothing to show for it.
    faces = {}
    for index in sorted(bitten):
        reach, ring = asked[index], rings.get(index, 0)
        washed = grown(index, reach, blocks(index), ring, FACE_FRACTION)
        if mass(washed['alpha']) >= FACE_KEEP * mass(
                bare(index, reach, FACE_FRACTION)['alpha']):
            continue          # barely touched: the wash comes out even enough
        rimmed = grown(index, reach, blocks(index), ring, 0.0)
        if mass(rimmed['alpha']) >= FACE_DROP * mass(
                bare(index, reach, 0.0)['alpha']):
            faces[index] = 0.0

    def at(index, reach):
        """A halo at a given reach, remembered: the search keeps asking for the
        same ones. Every halo goes through the clipper, since `expand` may grow one
        that fitted at first into a line it didn't reach before; one that meets
        nothing comes out of it untouched, because a keep-out it is already dark on
        is skipped."""
        if (index, reach) not in shaped:
            shaped[(index, reach)] = grown(
                index, reach, blocks(index),
                rings.get(index, 0), faces.get(index, FACE_FRACTION))
        return shaped[(index, reach)]

    def regions(halos, position):
        """Every region a touch on this item can put into the mask: its own frame,
        plus one companion for each halo it lights.

        A d-pad lights itself an arm at a time, and an arm is narrower than the
        halo it came out of: its long sides run through the middle of the region,
        where the d-pad's own glow has faded to nothing but a neighbour's may not
        have. So the arms are what gets measured, not the region they came from."""
        found = [masks[position]]
        for index, entry in halos.items():
            if index not in shown(position):
                continue
            if index == position and index in crosses:
                found += sorted(bands(index, entry).values())
            else:
                found += entry['pieces']
        return found

    def step(halos, positions):
        """The worst step each of those items would leave along its mask."""
        return {position: brightest(halos, regions(halos, position))
                for position in positions}

    def blame(halos, index, positions, cap=EDGE_TOLERANCE):
        """The worst step this one halo is on the hook for.

        The field is the brightest of every halo at each point, so the step along
        a boundary is the worst of what each halo contributes there. Each halo's
        share is therefore its own to fix by pulling in, and the skin is clean
        exactly when every share is -- which is what lets one halo be judged
        while its neighbours are still oversized.

        `cap` stops the walk once the answer is past caring; raise it to get a
        number worth comparing against another halo's."""
        alone = {index: halos[index]}
        worst = 0
        for position in positions:
            for _, found in steps(alone, regions(halos, position)):
                worst = max(worst, found)
                if worst > cap:
                    return worst
        return worst

    def affected(halos, index, span):
        """Which items a change to halo `index` can have altered: the ones that
        light it, whose mask changes shape with it, and the ones whose mask
        touches where the halo used to reach or now reaches."""
        return {position for position in range(len(items))
                if index in shown(position)
                or any(intersect(region, span)
                       for region in regions(halos, position))}

    def teams(halos):
        """The clusters that have to come out matching, as they stand: peers still
        carrying a halo and not among the lopsided, who are on their own by then."""
        return sorted({tuple(index for index in peers[first]
                             if index in halos and index not in clipped)
                       for first in halos if first not in clipped})

    def level(halos):
        """Peers back to a single reach, where anything has pulled them apart.

        `relax` and the trimming work an item at a time, so a cluster that started
        out matching can finish a step out of line. Levelling down is safe on its
        face -- a shorter halo is dark wherever a longer one was -- but its region
        comes in with it, and a neighbour's glow that was buried in the old, wider
        one can be left crossing the rim of the new one. So the whole field is
        measured again, and a cluster that can't be levelled without a seam keeps the
        mismatch, which is the lesser fault."""
        for unit in teams(halos):
            reaches = {halos[index]['asked'] for index in unit}
            if len(reaches) < 2:
                continue
            trial = {**halos, **{index: at(index, min(reaches)) for index in unit}}
            if max(step(trial, range(len(items))).values(),
                   default=0) <= EDGE_TOLERANCE:
                halos = trial
            elif DEBUG:
                print('   uneven', unit, sorted(reaches))
        return halos

    def relax(wearers):
        """Every halo at the reach asked for, then pulled in one at a time until
        none of them is cutting an edge."""
        halos = {index: at(index, asked[index]) for index in wearers}
        for _ in range(ROUNDS):
            settled = True
            for index in wearers:
                was = halos[index]['reach']
                trial = None
                for trim in TRIMS:
                    reach = max(floor, round(asked[index] * trim))
                    trial = {**halos, index: at(index, reach)}
                    span = union(halos[index]['region'], trial[index]['region'])
                    # A shorter reach is a worse glow, so take the first that fits.
                    if blame(trial, index,
                             affected(trial, index, span)) <= EDGE_TOLERANCE:
                        break
                halos = trial
                if halos[index]['reach'] != was:
                    settled = False
            if settled:
                break
        return halos

    # A button whose artwork is buried under someone else's frame has nowhere left
    # to fade to and comes out of the clip with nothing.
    halos = relax([index for index in silhouettes
                   if at(index, asked[index])['box'][2]
                   > at(index, asked[index])['box'][0]])

    # A halo can still be hemmed in past the point of trimming, where the clip had
    # to give up: a frame no bigger than twice the fade, say. A seam is worse than
    # no glow, so the halo most to blame goes -- and the rest start over from the
    # full reach, since the neighbour it was crowding may have room now.
    dropped = [index for index in silhouettes if index not in halos]
    while halos:
        bad = [position for position, value in step(halos, range(len(items))).items()
               if value > EDGE_TOLERANCE]
        if not bad:
            break
        blamed = max(halos, key=lambda index: blame(halos, index, bad, cap=255))
        if blame(halos, blamed, bad, cap=255) <= EDGE_TOLERANCE:
            break                       # nothing to pin it on; leave it reported
        if DEBUG:
            print('   drops', blamed, sorted(names[blamed]), 'blame',
                  blame(halos, blamed, bad, cap=255), 'bad', bad,
                  {index: blame(halos, index, bad, cap=255) for index in halos})
        del halos[blamed]
        dropped.append(blamed)
        halos = relax(sorted(halos))

    def expand(halos):
        """Let an even halo grow back into room the trimming took off it.

        The ladder comes down in fifths and the pixels only ever want a little less
        than the step it lands on, so a halo can finish well short of what it could
        hold. Once every halo is placed the pixels can settle it: a step up at a
        time, in turns, taking the step only while every mask it touches stays dark
        along its edges. Turns rather than one halo at a time to finish, so the slack
        goes round the neighbourhood instead of to whichever halo happens to be
        measured first.

        Past its half of the gap is allowed here, and only here. Half each is how the
        reaches are *decided*, so that no halo is talked out of its share by one that
        was measured first; what a halo actually keeps is settled by the pixels, and a
        neighbour that faded out well short of the middle has left room there that
        nothing else can use. Taking it is safe for the same reason everything else in
        this pass is: the step is kept only while every mask still finds every halo
        dark along its edges.

        Peers move as one: the step is drawn for the whole cluster and kept only if
        every one of them can hold it, so they stay the same size as each other all
        the way up. One growing alone is how a cluster ends up askew, and it is worth
        more to the eye that four halos match than that one of them is a pixel
        wider."""
        given = {index: halos[index]['asked'] for index in halos}
        # A lopsided halo grows too, on its own. It is the one that most needs to --
        # what made it lopsided was a rectangle across its artwork, which says nothing
        # about the sides it is free on -- and it is out of every cluster by then, so
        # there is nobody to keep in step with. The N64's A had a C-pad arm over its
        # bottom third and an inch of empty bezel above it.
        units = teams(halos) + [(index,) for index in sorted(halos) if index in clipped]
        for _ in range(ROUNDS):
            grew = False
            for unit in units:
                if not unit or max(given[index] for index in unit) >= wanted:
                    continue
                held = min(given[index] for index in unit)
                reach = min(wanted, max(held + 1, round(held / TRIMS[1])))
                trial, span = dict(halos), None
                for index in unit:
                    trial[index] = at(index, reach)
                    span = union(halos[index]['region'], trial[index]['region']) \
                        if span is None else union(span, trial[index]['region'])
                # The whole field, not just this halo's share: a longer reach moves
                # the region as well, and a neighbour that was dark inside the old
                # one may not be inside the new one.
                touched = set()
                for index in unit:
                    touched |= affected(trial, index, span)
                if max(step(trial, touched).values(), default=0) <= EDGE_TOLERANCE:
                    halos, grew = trial, True
                    for index in unit:
                        given[index] = reach
            if not grew:
                break
        return halos

    halos = level(expand(halos))

    # A halo can come through the trimming intact and still hold nothing. A d-pad
    # only glows outside its own frame, and on a skin where every side of it is
    # somebody else's frame the clipping can take the whole strip. Calling that
    # unlit is more use than a companion that lights nothing.
    for index in sorted(halos):
        if mass(halos[index]['alpha']) < EMPTY_SHARE * max(1.0, mass(bare(
                index, halos[index]['asked'],
                faces.get(index, FACE_FRACTION))['alpha'])):
            if DEBUG:
                print('   culls', index, sorted(names[index]),
                      mass(halos[index]['alpha']))
            del halos[index]
            dropped.append(index)

    def worn(position):
        """The companions a touch on this item needs, as (region, extended frame):
        one per halo it lights, and for a d-pad pressing itself, one per arm.

        A d-pad's own companions are pinned to its directional zones, so its bloom
        arrives in the direction being pushed. Anything else that fires the same
        inputs -- a separate button wired to `up`, say -- has no zones to pin to and
        cannot say which way anything is being pushed, so it lights the whole
        halo.

        Halos this item shares a mask with come along whole, which is what keeps
        them from being cut: see `share`."""
        found = []
        for index, entry in sorted(halos.items()):
            if index not in shown(position):
                continue
            if index == position and index in crosses:
                zoned = zones(items[index], rep)
                found += [(piece, zoned[side])
                          for side, piece in sorted(bands(index, entry).items())]
            else:
                found += [(piece, extended_box(items[position], rep))
                          for piece in entry['pieces']]
        return found

    worst = step(halos, range(len(items)))
    extra = [companion(scaled(piece, to_units), extended)
             for position in range(len(items))
             for piece, extended in worn(position)]

    if report is not None:
        for index in sorted(dropped):
            report.append('%d: no room for a glow at all -- left unlit' % index)
        for index, entry in sorted(halos.items()):
            if entry['asked'] < wanted:
                report.append('%d: reaches %.1fpt, not %.1fpt -- %s'
                              % (index, entry['asked'] / ppp, points,
                                 "a neighbour's glow leaves it no room at all"
                                 if index in clipped
                                 else "as far as it can without lighting a neighbour"))
            # Against the same halo with nothing taken out of it -- the same reach
            # and the same face -- so a halo that was given a shorter reach and kept
            # all of it says nothing here.
            kept = mass(entry['alpha']) / max(1.0, mass(bare(
                index, entry['asked'],
                faces.get(index, FACE_FRACTION))['alpha']))
            if DEBUG and kept < 0.85:
                whole = bare(index, entry['asked'],
                             faces.get(index, FACE_FRACTION))['alpha']
                for box in blocks(index):
                    one = clip(whole, entry['offset'], [box],
                               min(entry['asked'] * CLIP_FADE, CLIP_REACH * ppp))
                    if mass(one) < 0.98 * mass(whole):

                        print('   cut', index, sorted(names[index]), box,
                              'rim', along(whole, entry['offset'], [box]),
                              'keeps %d%%' % round(100 * mass(one)
                                                   / max(1.0, mass(whole))))
            if kept < 0.85:
                report.append('%d: keeps %d%% of its glow -- %s' % (
                    index, round(100 * kept),
                    'even ring %.1fpt, bloom hemmed in on some sides'
                    % (rings[index] / ppp) if index in rings
                    else 'hemmed in on some sides'))
            together = sorted(shown(index) & set(halos) - {index})
            if together:
                report.append('%d: lights with %d other halo%s, all of them whole'
                              % (index, len(together),
                                 '' if len(together) == 1 else 's'))
        for position, value in sorted(worst.items()):
            if value <= EDGE_TOLERANCE:
                continue
            live = regions(halos, position)
            found, culprit = max(((found, index) for index, found
                                  in steps(halos, live)), key=lambda pair: pair[0])
            box = live[culprit]
            report.append('%d: %s cuts the glow at %d/255 -- a visible edge'
                          % (position, 'its own frame' if culprit == 0
                             else 'a companion %dx%d' % (box[2] - box[0],
                                                        box[3] - box[1]), found))

    field = Image.new('L', size, 0)
    for entry in halos.values():
        paste_lighter(field, entry['alpha'], entry['offset'])
    return field, extra, halos


def paste_lighter(field, alpha, offset):
    """`alpha` onto `field` at `offset`, keeping whichever is brighter, clipped to
    the image -- an overlay may legitimately hang off the edge of a skin."""
    box = intersect((offset[0], offset[1],
                     offset[0] + alpha.width, offset[1] + alpha.height),
                    (0, 0, field.width, field.height))
    if box is None:
        return
    patch = alpha.crop((box[0] - offset[0], box[1] - offset[1],
                        box[2] - offset[0], box[3] - offset[1]))
    field.paste(ImageChops.lighter(field.crop(box), patch), (box[0], box[1]))


def apply(base, field, opacity=GLOW_OPACITY, color=GLOW_COLOR):
    """`base` with the glow laid over it wherever `field` says to: the pressed
    image.

    White reads as light and works on any shell dark enough to show it. On a pale
    shell there is nothing for it to contrast against -- a lit button and its
    surround are both near white -- and a colour is the only way to be seen."""
    alpha = field.point(lambda v: round(v * opacity)) if opacity != 1.0 else field
    over = Image.new('RGBA', base.size, tuple(color) + (255,))
    over.putalpha(alpha)
    pressed = base.copy()
    pressed.alpha_composite(over)
    return pressed


def pressed_name(asset):
    """DeltaCore's companion filename: `_pressed` before the extension."""
    stem, dot, extension = asset.rpartition('.')
    return '%s_pressed%s%s' % (stem, dot, extension) if dot else asset + '_pressed'
