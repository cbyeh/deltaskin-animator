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
one (`notched`), which leaves out the corners where two insets meet. The four insets
are independent, and a one-sided halo needs them to be: a corner comes off only where
the glow has left it empty, which is where the halo has bloomed on one side and not
on the neighbouring one -- and what a companion reaches over is exactly what its
neighbours lose. Each cut is the deepest that leaves both the corner itself and the
union's boundary dark, and the smaller of the disc and the notched box wins by area.
Because the two pieces overlap, the lines where they meet lie inside the union and
are never measured as an edge.

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

None of it touches the button's own face. The halo is a ring outside the artwork
and the artwork is left exactly as it was drawn, which is what makes a fade safe to
do at all: the rectangle a halo is dodging often crosses the button itself, and a
wash dimmed across a button you are holding reads as the button lighting unevenly
rather than as a light beside it.

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

# The shoulders take a thin outline instead of a bloom, however much room they have.
# They sit along the top edge with the whole corner of the shell to themselves, so
# the packing hands them the most reach on the skin -- 28.7pt on the DS against 7.3pt
# for a face button -- and the result is a lopsided one: a wide soft bloom on the
# open side, and on the side something is in the way, the fade cut off inside its own
# bright core, which is a hard bright line with a straight edge. The N64's landscape
# `l` and `r` had 48px of bloom above and 10px below ending at full strength. A thin
# ring is even on every side without asking anything of the room, which is what these
# buttons want: they are long, they are already at the edge of the picture, and an
# outline round one reads as clearly as a bloom.
SHOULDER_INPUTS = frozenset({'l', 'r', 'l2', 'r2', 'l3', 'r3'})
SHOULDER_POINTS = 4.0

GLOW_COLOR = (255, 255, 255)   # what the glow is made of; white unless asked

# A shell too pale for white to be seen against gets this instead; see
# `suggest_color`, which is what `--glow-color auto` asks for. Warm, because a
# lit button is a light and a light is warm, and the amber the original
# reference shot used reads as a glow on a grey plate where white reads as paint.
GLOW_WARM = (255, 179, 0)
# Base luminance under a halo above which white stops reading as light. Set from the
# skins themselves, whose palest halo sits on 142 (the SNES shell), 130 (the NES's
# silver button plate), 120 (the N64's A/B plate), then 71, 43, 37, 36 -- so anything
# between about 75 and 120 divides them the way the eye does. Middling grey is the
# hard case: white on it is neither light nor paint, and 115 calls it pale.
PALE_LEVEL = 115

GLOW_OPACITY = 1.0       # the colour at its strongest, just outside the artwork

# How much of a wash the button's own face gets, relative to that. None: the
# halo is a ring *outside* the artwork and the button is left exactly as it was
# drawn. White over the face lifts the whole button towards white -- the SNES's
# A went pale lavender, the DS's a pale grey -- which is a button that has lost
# its colour rather than a button with a light around it, and it hides the very
# artwork whose sinking is the other half of the feedback. Kept as a knob because
# the profile below is written in terms of it.
FACE_FRACTION = 0.0
FALLOFF = 0.85           # fade exponent: 1 is linear, lower stays bright further out

# Of the reach held at full strength before the fade begins, and of the reach that
# core then takes to rejoin the fade. A ring outside the artwork is all the glow
# there is now, and how *wide* it can be is decided by the buttons next door -- a
# face button in a diamond gets 10 points and no argument. What is left to decide
# is how much of that width is solid, and the answer is most of it: a band of flat
# white with a short fade off the end reads as a ring, where a gradient over the
# same distance reads as a smudge. The fade is what every neighbour is measured
# against, so the core drops steeply back onto it and the last levels are left
# exactly where they were.
GLOW_CORE = 0.55
GLOW_EDGE = 0.2
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

# And the floor for a single arm of a d-pad, which needs a much higher one. Its
# glow is one
# arm at a time, so the little that survives a heavy clip isn't a thin ring round
# the button -- it is whichever piece of the strip happened to fall outside every
# neighbour's frame, which can be a patch of bezel nowhere near what is being
# pressed. The N64's C buttons are the case: their pad is one item covering the
# whole cluster, glow inside it would light all four at once, and what is left
# outside is a bright bar floating above the top button. A press that lights
# nothing reads as a skin without glow on that button; a press that lights a
# stray patch reads as a bug.
CROSS_EMPTY = 0.25

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

# Reaches to try, as fractions of the one asked for, when something is in the way.
TRIMS = (1.0, 0.85, 0.72, 0.6, 0.5, 0.42, 0.34, 0.28, 0.23, 0.18)

ROUNDS = 4               # relaxation passes; one halo shrinking can free another

# When a d-pad's four arms are levelled to the shortest of them (`evened`): only if
# the longest is at least `LEVEL_RATIO` times the shortest, so a cross whose arms
# differ by a few pixels keeps every one of them, and only if the shortest is still
# `LEVEL_FLOOR` points long, so three good arms are never cut back to a stub.
LEVEL_RATIO = 2.0
LEVEL_FLOOR = 10.0

# A halo that blooms further one way than another needs a mask shaped like the bloom,
# and a rectangle or a disc holding a lobe holds a lot of skin that the lobe doesn't
# reach -- skin that may be a neighbour's glow, which is what caps the bloom in the
# first place. `staircase` cuts the box into this many overlapping bands instead, each
# pulled in to the glow its own rows really carry. Bands overlap by `STAIR_SEAM`, so
# that where two of them meet each buries the other's rim (see `boundary`); and a
# staircase is only taken where it saves at least this much of the simpler shape,
# since every band is another item in the skin.
STAIR_CUTS = (2, 3, 4)
STAIR_SEAM = 3
STAIR_GAIN = 0.92

# A round halo blooming one way is carried by a disc over its even ring and a
# staircase over the bloom past it (`carried`). These are the fractions of the reach
# the disc is tried at, measured from the artwork out: too large and it is the bulging
# disc again, too small and its rim comes out through the middle of the light. And
# `LOBE_FULL` is how much of its own disc a halo has to have gone dark in before the
# split is worth looking for at all -- an even halo is a disc and wants a disc.
LOBE_SHARES = (0.85, 0.72, 0.6, 0.5)
LOBE_FULL = 0.92

# How many pixels in from the halo's own edge a disc is allowed to be tried. A halo
# ends in a blur whose last pixels are worth a level or two out of 255, and a disc
# sized to hold every one of them carries that dead tail all the way round its rim --
# which on a diamond of buttons is the whole of what puts it back over its neighbours.
# Every rung is offered as a shape of its own and answers to the same test as the
# rest: a disc that cuts light the eye can see is thrown out (`fits`), so the ladder
# reaches only as far in as the tail is dark, and the smallest one that holds wins.
DISC_TRIMS = 10

ROUND = 'circle'         # DeltaCore's name for a disc-shaped mask
ROUND_SLACK = 2          # px a disc may miss the shape it is standing in for

# How far past the artwork a companion must reach on an item whose halo fills the
# ring its press vacates (`wearing`). Two pixels: one to bury the frame's own rim,
# one for the rounding between a frame in mapping units and the pixels it lands on.
INSIDE_SLACK = 2

# How close to the edge of the display an item's artwork counts as sitting on it,
# which decides whether its halo fades before that edge or runs off it (`lines`).
FLUSH_SLACK = 3


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
    edge, and by default the artwork itself is left alone: what the eye is being
    shown is a ring of light around the button, not a button painted white.

    The fade is slightly concave (`FALLOFF` below 1) because how far a halo may
    reach is set by its neighbours, not by how bright it is: a reach is a fixed
    budget, and a fade that has dropped below what a screen can show halfway
    through has spent the second half of that budget on nothing. Staying bright
    almost to the end and then dropping is what a crowded cluster can afford.

    `face` is a wash over the artwork itself, which is `FACE_FRACTION` -- none --
    everywhere: a d-pad because its arrows and its tilt are the feedback and white
    over them erases both, and a button because a ring reads as light and a pale
    button reads as the wrong colour.

    `dist` is a `depths` field already built for this silhouette, of at least this many
    rings; without one it is built here."""
    rings = max(1, round(reach * (1.0 - BLUR_FRACTION)))
    sigma = max(0.6, (reach - rings) / 3.0)
    if dist is None:
        dist = depths(art, rings)

    # A core of full strength before the fade starts. What a halo is laid over is
    # never one flat colour -- a button sits in a dish, with its own shadow on one
    # side of it and bare shell on the other -- and a colour laid on at half alpha
    # takes half of whatever is underneath with it. A ring that spends most of its
    # width at those middling strengths therefore comes out bright where the shell
    # is pale and dull where the shadow is, which reads as a lopsided glow even when
    # the glow itself is a perfect circle. Opaque out to `GLOW_CORE` of the way,
    # the band the eye actually follows is the same white all the way round, and
    # only the fade past it picks up what it lies on.
    #
    # Laid over the fade rather than replacing it, and dropping steeply enough to
    # rejoin it well before the end: what a halo may reach is decided entirely by
    # its last few levels -- the tolerance every rectangle in this arrangement is
    # measured against is 6 out of 255 -- so a core that brightened the tail as well
    # would buy its even ring with a shorter one. It cost the N64's B its glow
    # outright before the two curves were separated.
    def level(step):
        outer = (step - 0.5) / rings
        core = max(0.0, 1.0 - max(0.0, outer - GLOW_CORE) / GLOW_EDGE)
        return round(255 * max(1.0 - outer, core) ** FALLOFF)

    alpha = dist.point([0] + [level(step) if step <= rings else 0
                              for step in range(1, 256)])
    if face:
        alpha.paste(round(255 * face), (0, 0), art)
    return alpha.filter(ImageFilter.GaussianBlur(sigma))


def concentric(box, frame):
    """The largest rectangle inside `frame` that is centred on `box`.

    `visible` grows a silhouette out to the touch frame on the grounds that the
    frame is a rectangle centred on the button. Some of them aren't: the SNES's
    landscape shoulder is a 397x48 slab in a 400x54 frame with all six of those
    pixels *below* the button, over the shell's shadow. Grown to that frame the
    silhouette ends six pixels below the button's bottom edge and level with its
    top, so the ring outside it hangs off the bottom -- which is what a misaligned
    outline looks like. Pulling the loose side back in until the rectangle is
    centred on the artwork again can only give up reach the artwork never had."""
    span = []
    for axis in (0, 1):
        middle = (box[axis] + box[axis + 2]) / 2.0
        reach = min(middle - frame[axis], frame[axis + 2] - middle)
        if reach <= 0:
            return frame
        span.append((round(middle - reach), round(middle + reach)))
    return (span[0][0], span[1][0], span[0][1], span[1][1])


def clipped(box, bounds, slack=FLUSH_SLACK):
    """Which of `box`'s sides are the edge of the picture, in image pixels.

    A side that is tells you the artwork's bounding box is not the artwork's shape:
    part of the button is off the picture, and nothing measured along that side is
    the button's."""
    sides = {'left'} if box[0] <= slack else set()
    if box[1] <= slack:
        sides.add('top')
    if box[2] >= bounds[0] - slack:
        sides.add('right')
    if box[3] >= bounds[1] - slack:
        sides.add('bottom')
    return frozenset(sides)


def widen(box, radius, cut):
    """`box` with each side listed in `cut` pushed out far enough to fit `radius`.

    A shoulder button sits on the edge of the display and runs off it, so what is
    visible of one is a rounded rectangle with a side missing -- and its corners can
    be rounder than anything the visible part could hold. The SNES's landscape `l`
    shows 397x48 of a slab whose bottom corners have a radius of 52, which needs 104
    pixels of height; the other 56 are above the top of the picture."""
    edge = list(box)
    if 'left' in cut:
        edge[0] = min(edge[0], edge[2] - 2 * radius)
    if 'right' in cut:
        edge[2] = max(edge[2], edge[0] + 2 * radius)
    if 'top' in cut:
        edge[1] = min(edge[1], edge[3] - 2 * radius)
    if 'bottom' in cut:
        edge[3] = max(edge[3], edge[1] + 2 * radius)
    return tuple(edge)


def rounded(mask, box, cut):
    """The rounded rectangle the artwork is: its own bounds, and its corner radius.

    Read off the outline, a radius comes out too small. A rounded rectangle's last
    row runs from `x0 + r` to `x1 - r` in the corner's *geometry*, but the pixels in
    that row are the ones the arc passes through, half a pixel above its widest
    point, so they reach `sqrt(r^2 - (r - 0.5)^2)` further out -- seven pixels on a
    radius of 52. Measuring the DSXL's landscape shoulder that way gave 44 for a
    corner that is actually 53.

    So the radius is the one whose rounded rectangle *agrees with* the silhouette
    best, over every pixel of it rather than its outline: on the N64's shoulder,
    where the straight part of the side can be counted directly and settles the
    question exactly, that is 49 against the 49.5 the count gives. Every candidate
    takes its box from `widen`, so a shape running off the picture is fitted as the
    whole shape it is part of."""
    want = mask.crop(box).point(lambda v: 255 if v > EDGE_TOLERANCE else 0)
    wide, high = want.size
    # A radius is bounded by half the shorter side -- of the sides that are the
    # button's own. Where neither axis is, there is nothing to bound it but the box.
    limits = ([wide // 2] if not {'left', 'right'} & cut else []) \
        + ([high // 2] if not {'top', 'bottom'} & cut else [])
    best, agreement = 0, None
    for radius in range(0, (min(limits) if limits else max(wide, high) // 2) + 1):
        edge = widen(box, radius, cut)
        shape = Image.new('L', (edge[2] - edge[0], edge[3] - edge[1]), 0)
        ImageDraw.Draw(shape).rounded_rectangle(
            (0, 0, shape.width - 1, shape.height - 1), radius=radius, fill=255)
        at = (box[0] - edge[0], box[1] - edge[1])
        wrong = sum(count for level, count in enumerate(ImageChops.difference(
            shape.crop((at[0], at[1], at[0] + wide, at[1] + high)), want).histogram())
            if level > 127)
        if agreement is None or wrong < agreement:
            best, agreement = radius, wrong
    return widen(box, best, cut), best


def slab(mask, box, frame, cut):
    """A shoulder's silhouette: one clean rounded rectangle over its artwork.

    Everywhere else the silhouette is the flooded artwork with the touch frame
    filled in behind it, and a few ragged pixels along its outline cost nothing --
    a bloom twenty rings deep has smoothed them away long before its last level. An
    outline four points wide has not: every lump in the silhouette is a lump in the
    ring, and on a long button the eye follows that ring for four hundred pixels.
    So a shoulder's silhouette is drawn rather than flooded, at the shape `rounded`
    measures, which is also what stops the ring rounding off a corner the button
    doesn't have -- or holding a corner where the button has an arc.

    Where that shape runs off the picture it is drawn running off it, and the canvas
    clips the raster rather than the geometry, so the arcs that are on the picture
    are the button's arcs."""
    edge, radius = rounded(mask, box, cut)
    want = union(concentric(edge, frame), edge)
    grown = Image.new('L', mask.size, 0)
    ImageDraw.Draw(grown).rounded_rectangle(
        (want[0], want[1], want[2] - 1, want[3] - 1), radius=radius, fill=255)
    return grown


def visible(mask, box, frame, cap, hug=False, cut=frozenset()):
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

    `hug` asks for the shape to be the button's rather than the frame's: the
    rectangle `rounded` measures off the artwork, with the frame pulled in until it
    is centred on that (`slab`). It is the shoulders that ask for it, because an
    outline four points wide takes its whole shape from the silhouette where a bloom
    only took its size. `cut` says which of the artwork's sides are the edge of the
    picture, which is what lets a shoulder be fitted as the whole button it is part
    of rather than as the part of it that shows; see `clipped`. Square frames are
    left alone even then: their halo is drawn from the circle inscribed in the frame,
    and that circle being the frame's is what keeps the ring exactly round.

    Returns the silhouette and, where the shape it grew to is a circle, that circle
    -- which is what lets the halo around it be drawn exactly round; see `radial`."""
    if any(inset > cap for inset in (box[0] - frame[0], box[1] - frame[1],
                                     frame[2] - box[2], frame[3] - box[3])):
        return mask, None
    if hug and abs((frame[2] - frame[0]) - (frame[3] - frame[1])) > 2 * ROUND_SLACK:
        return slab(mask, box, frame, cut), None
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


def shoulder(item):
    """Whether an item is one of the shoulder buttons.

    A shoulder is a shoulder by its input, not its shape: `l` and `r` are drawn as a
    capsule on some of these skins, a plain rounded slab on others and a round button
    on the GBA, and all three want the same thin ring. See `SHOULDER_POINTS`."""
    names = input_names(item)
    return bool(names) and names <= SHOULDER_INPUTS


def footprint(art, offset, frame, pad, cross=False, hug=False, bounds=None):
    """The silhouette a halo grows from, on a canvas with room for the halo.

    A halo reaches further out than the crop its artwork was found in has room
    for, so each silhouette moves onto a canvas of its own -- which also keeps the
    ring dilations off all the empty space around it. A d-pad keeps the silhouette
    it was found with: its frame is a square around a cross, and filling that
    square would put solid glow in the corners, where the shape of the thing being
    pressed is.

    Returns the mask, where its top-left corner sits in image pixels, the box its
    artwork occupies, and the circle it was grown to if it was grown to one --
    `None` where `art` is empty.

    `bounds` is the size of the picture, which is the one thing about a button that
    can't be seen in the button: whether an edge of its artwork is where the button
    ends or where the picture does (`clipped`).

    This is also the boundary the item's *overlay* is cut to (`animate.py`), which
    is why it lives out here rather than inside `build`. The two have to be the
    same shape to the pixel: the overlay is drawn on top of the halo, so any of the
    button's surroundings it carries is halo the device never shows."""
    span = art.getbbox()
    if span is None:
        return None
    box = (offset[0] + span[0], offset[1] + span[1],
           offset[0] + span[2], offset[1] + span[3])
    want = box if cross else union(box, frame)
    origin = (want[0] - pad, want[1] - pad)
    canvas = Image.new('L', (want[2] - want[0] + 2 * pad, want[3] - want[1] + 2 * pad))
    canvas.paste(art.crop(span), (box[0] - origin[0], box[1] - origin[1]))
    circle = None
    if want != box:
        def local(rect):
            return (rect[0] - origin[0], rect[1] - origin[1],
                    rect[2] - origin[0], rect[3] - origin[1])
        canvas, circle = visible(canvas, local(box), local(frame),
                                 round(RIM_SHARE * min(frame[2] - frame[0],
                                                       frame[3] - frame[1])), hug,
                                 clipped(box, bounds) if bounds else frozenset())
        span = canvas.getbbox()
        box = (origin[0] + span[0], origin[1] + span[1],
               origin[0] + span[2], origin[1] + span[3])
    return {'mask': canvas, 'origin': origin, 'box': box,
            'circle': None if cross else circle}


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


def reaching(length, edge, away, cap, fade):
    """A 0-255 weight along one axis: full at `edge` and for `cap - fade` past it in
    the `away` direction, then a ramp to nothing by `cap`.

    One-sided, unlike `profile`: an arm cut back to length keeps all of its base --
    the brightest part, right against the artwork -- and loses only its tip."""
    fade = max(1, int(round(min(fade, cap))))
    levels = []
    for position in range(length):
        far = (position - edge) * away
        levels.append(255 if far <= cap - fade else
                      0 if far >= cap else round(255 * (cap - far) / fade))
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


def arms(alpha, frame, fade, mouths, caps=None):
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
    whose arms reach past its frame has no gap and needs no fade.

    `caps` optionally holds a length in pixels per side, past which that arm ramps
    away to nothing (`reaching`). One arm can have far less room than the other
    three -- the N64's up arm has the thumbstick 49px above it -- and four arms of
    obviously different lengths read as a mistake, so the rest can be cut back to
    match it. Only the tips go: the length is measured out from the frame's edge and
    the ramp is one-sided, leaving the bright base against the artwork untouched."""
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
        length = height if outer == 0 else width
        rise = Image.new('L', (1, height) if outer == 0 else (width, 1))
        rise.putdata(profile(length, span[0], span[1], inset))
        arm = ImageChops.multiply(arm, rise.resize(alpha.size, Image.NEAREST))
        cap = (caps or {}).get(side)
        if cap is not None:
            tip = Image.new('L', (1, height) if outer == 0 else (width, 1))
            tip.putdata(reaching(length, edge, away, cap,
                                 min(fade, max(2, cap / 3.0))))
            arm = ImageChops.multiply(arm, tip.resize(alpha.size, Image.NEAREST))
        weight = ImageChops.lighter(weight, arm)
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


def notched(box, insets):
    """`box` as two overlapping rectangles -- one inset `top` and `bottom`, one inset
    `left` and `right` -- which leaves out the corners where two insets meet.

    A halo is round and its box is not, so the corners of the box hold nothing --
    and they are what reaches furthest towards a button sitting diagonally away,
    where its own artwork can end up inside them. Handing the mask two rectangles
    instead of one keeps the same glow and gives the diagonal neighbour its room
    back. They overlap, so the lines where they meet lie inside the union.

    The four insets are independent, which is what a one-sided halo needs. A glow
    that blooms up and to the right and dies out before the button below it has one
    corner worth keeping and three worth cutting deep, and cutting all four to the
    depth the brightest of them allows is barely cutting them at all. A corner is
    left out exactly where both of its insets reach it, so `top` and `left` alone
    take out the top-left corner and nothing else."""
    top, bottom, left, right = insets
    return [(box[0], box[1] + top, box[2], box[3] - bottom),
            (box[0] + left, box[1], box[2] - right, box[3])]


def staircase(alpha, offset, box, keep, cuts, axis, seam=STAIR_SEAM):
    """`box` as a stack of `cuts` rectangles across `axis`, each pulled in across to
    the glow its own rows hold -- the shape of the glow rather than the shape of its
    bounding box.

    This is what lets a halo be longer on one side than the other. A bloom is capped
    not by where its own light reaches but by what the rectangle carrying it covers:
    a disc or a box big enough to hold a lobe reaching up also reaches down, and if
    a neighbour's glow is down there, pressing this button lights it. Cut into bands,
    the mask follows the lobe up and stays off the neighbour, and the halo gets to
    keep the room it actually has.

    Two details make it safe. The bands overlap, because `boundary` erases a sibling
    a pixel shy of its own rim: butted together, the rim where two bands meet would
    count as an edge on show though the mask has no seam there at all. And every band
    holds the frame's own slice as well as the glow's, since the frame is live
    alongside the companion whenever the item itself is pressed and a rim sticking
    out through the side of the staircase is an edge like any other.

    Returns `None` where `box` is too short across to be worth cutting."""
    across = 1 - axis
    low, high = box[axis], box[axis + 2]
    if high - low < cuts * (2 * seam + 2):
        return None
    lit = alpha.point(lambda level: 255 if level > EDGE_TOLERANCE else 0)
    edges = [low + int(round((high - low) * step / float(cuts)))
             for step in range(cuts + 1)]
    pieces = []
    for step in range(cuts):
        start = max(low, edges[step] - (seam if step else 0))
        stop = min(high, edges[step + 1] + (seam if step < cuts - 1 else 0))
        band = [0, 0, alpha.width, alpha.height]
        band[axis], band[axis + 2] = start - offset[axis], stop - offset[axis]
        found = lit.crop(tuple(band)).getbbox()
        if found is None:
            continue
        edge = [band[axis] + offset[axis], band[axis + 2] + offset[axis]]
        side = [found[across] + band[across] + offset[across] - 1,
                found[across + 2] + band[across] + offset[across] + 1]
        if keep is not None and keep[axis] < stop and keep[axis + 2] > start:
            side = [min(side[0], keep[across]), max(side[1], keep[across + 2])]
        piece = [0, 0, 0, 0]
        piece[axis], piece[axis + 2] = edge
        piece[across], piece[across + 2] = (max(side[0], box[across]),
                                            min(side[1], box[across + 2]))
        if pieces and pieces[-1][across] == piece[across] \
                and pieces[-1][across + 2] == piece[across + 2]:
            pieces[-1] = union(pieces[-1], tuple(piece))   # one band, not two
        else:
            pieces.append(tuple(piece))
    return pieces or None


def stretched(box, span, frame):
    """`box` widened to the whole of `span` across, where it sits off one flank of
    `frame` and `span` reaches past both its ends.

    A halo has to be dark inside any rectangle a neighbour's press puts on show, and
    the clipper sees to that -- but dark inside is not the same as kept out. A small
    button off one flank leaves the glow free to reach round it, above and below, and
    then the smallest rectangle holding that glow holds the neighbour's rectangle too,
    and the neighbour's glow with it: pressing this button lights the little one
    beside it. The N64's A has `r` 31px off its right flank and half its height, and
    A's own bloom was curling round it.

    So where the glow would wrap, the keep-out is stretched and the glow stops flat
    against it instead -- which is what leaves the box holding it a plain rectangle,
    free to bloom on the sides where there is room. Nothing is stretched where the
    neighbour already covers the span, or where it lies across a corner: a corner is
    what `notched` takes out, and taking one out costs the glow nothing.

    A disc comes back as its bounding rectangle. Stretched, a disc is no longer the
    shape it was standing in for, and the wider keep-out is the safe way to be wrong
    -- it costs a little glow, where the other way round lights a neighbour."""
    for axis in (0, 1):
        across = 1 - axis
        if box[axis + 2] > frame[axis] and box[axis] < frame[axis + 2]:
            continue                    # not off that flank: overlaps the frame
        if box[across] > span[across] and box[across + 2] < span[across + 2]:
            wide = list(box[:4])
            wide[across], wide[across + 2] = span[across], span[across + 2]
            return tuple(wide)
    return box


def covers(pieces, shape):
    """Whether the union of `pieces` covers every pixel of `shape`."""
    offset, size = (shape[0], shape[1]), (max(1, shape[2] - shape[0]),
                                          max(1, shape[3] - shape[1]))
    want = solid(size, shape, offset)
    for piece in pieces:
        if intersect(piece, shape) is None:
            continue
        want = ImageChops.subtract(want, solid(size, piece, offset))
    return want.getbbox() is None


def area(pieces):
    """How much of the skin the union of `pieces` puts into the mask -- what a
    companion costs its neighbours, and the one number two shapes for the same halo
    can be compared by. A disc counts as the disc and not as the box it sits in."""
    if not pieces:
        return 0
    span = pieces[0]
    for piece in pieces[1:]:
        span = union(span, piece)
    size = (max(1, span[2] - span[0]), max(1, span[3] - span[1]))
    filled = Image.new('L', size, 0)
    for piece in pieces:
        filled = ImageChops.lighter(filled, solid(size, piece,
                                                  (span[0], span[1])))
    return filled.histogram()[255]


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


def revealed(entry, regions):
    """The brightest a halo gets inside the union of `regions`: how much of it a
    press putting those rectangles into the mask would light up.

    `steps` doesn't answer this and can't. A companion big enough to swallow a
    neighbour's glow whole leaves no edge anywhere across it, so the pixels come out
    perfectly clean while the wrong button lights up -- the one thing the whole
    arrangement exists to prevent."""
    stencil = Image.new('L', entry['alpha'].size, 0)
    for box in regions:
        if intersect(box, entry['box']) is None:
            continue
        stencil = ImageChops.lighter(
            stencil, solid(entry['alpha'].size, box, entry['offset']))
    return ImageChops.darker(entry['alpha'], stencil).getextrema()[1]


def brightest(halos, regions):
    """The worst of those steps, giving up as soon as one is too big to accept."""
    worst = 0
    for _, found in steps(halos, regions):
        worst = max(worst, found)
        if worst > EDGE_TOLERANCE:
            break
    return worst


def build(rep, size, sources, points, ppp, report=None, sharing=GLOW_SHARE,
          vacated=None):
    """Work out every halo, and the companion items that let them be seen.

    `sources` maps an item's index to (silhouette, offset) in image pixels.
    Returns the glow laid over the whole image, the companions to append to
    `rep['items']`, and what each halo settled on.

    `vacated` maps an item's index to (mask, offset): the ring of its own artwork
    that a press slides out of, which the halo has to fill at full strength -- see
    `insides` below.

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

    # Each silhouette onto a canvas with room for its halo; see `footprint`.
    silhouettes, arts, circles = {}, {}, {}
    for index, (art, offset) in sources.items():
        found = footprint(art, offset, frames[index],
                          round(wanted * max(1.0, CROSS_REACH)) + 4,
                          directional(items[index]), shoulder(items[index]), size)
        if found is None:
            continue
        canvas, origin, box = found['mask'], found['origin'], found['box']
        if found['circle'] is not None:
            circles[index] = found['circle']
        silhouettes[index] = (canvas, origin)
        arts[index] = box
    crosses = {index for index in silhouettes if directional(items[index])}
    shoulders = {index for index in silhouettes if shoulder(items[index])}
    ceiling = {index: max(1, round(SHOULDER_POINTS * ppp)) if index in shoulders
                      else wanted
               for index in silhouettes}

    # The ring of its own artwork a press slides out of, at full strength, in the
    # halo's coordinates.
    #
    # The overlay DeltaCore moves is drawn above the halo, and when it shrinks it
    # uncovers a ring of whatever is behind it. Behind it during a press is this
    # image -- the base with every halo on it -- and the base still has the button
    # painted where it used to be, so that ring would show the button's old edge:
    # the ghost outline the band of surrounding background used to be there to
    # cover. That band is what was painting the halo out. Filling the ring with
    # opaque glow instead covers the old edge with light, which is both what the
    # eye should see under a sinking button and what lets the overlay be cut to the
    # artwork alone.
    #
    # It only ever adds glow *inside* the silhouette, so every outer level -- which
    # is what the reach search and the 6/255 edge tolerance are measured on -- is
    # untouched. What it does add is a 255 step where there was none, in a place a
    # mask region used to be free to end: over the artwork. So a region that carries
    # a ring has to reach past it, out where the glow has faded (`wearing`, and for a
    # d-pad's arms `INSIDE_SLACK` in `bands`).
    insides, seams = {}, {}
    for index, ring in (vacated or {}).items():
        if index not in silhouettes:
            continue
        canvas, origin = silhouettes[index]

        def held(mask, offset=ring['offset'], canvas=canvas, origin=origin):
            """`mask` on the halo's canvas, and only where the artwork is."""
            stencil = Image.new('L', canvas.size, 0)
            stencil.paste(mask, (offset[0] - origin[0], offset[1] - origin[1]))
            return ImageChops.multiply(
                stencil.point(lambda v: 255 if v > EDGE_TOLERANCE else 0), canvas)

        insides[index] = held(ring['mask'])
        if index in crosses and ring.get('states'):
            # How far back inside the frame each arm's rectangle has to reach to bury
            # its own ring.
            #
            # Which ring is its own is a question of zones: a press lights the arms
            # for the directions it holds, and what it uncovers falls inside those
            # arms' zones -- a diagonal uncovers a piece at each of the two tips, one
            # for each arm, and neither arm has to answer for the other's. Charging
            # every arm with the whole of what a diagonal uncovers would have the up
            # arm reaching to the far side of the cross, and its rectangle would then
            # light the ring right round the shape.
            frame, zoned = frames[index], zones(items[index], rep)
            edges = {'up': lambda box: box[3] - frame[1],
                     'down': lambda box: frame[3] - box[1],
                     'left': lambda box: box[2] - frame[0],
                     'right': lambda box: frame[2] - box[0]}
            seams[index] = {}
            for state, mask in ring['states'].items():
                lifted = held(mask)
                for side in state.split('+'):
                    zone = scaled(zoned[side], to_pixels)
                    patch = intersect(zone, (origin[0], origin[1],
                                             origin[0] + lifted.width,
                                             origin[1] + lifted.height))
                    span = None if patch is None else lifted.crop(
                        (patch[0] - origin[0], patch[1] - origin[1],
                         patch[2] - origin[0], patch[3] - origin[1])).getbbox()
                    if span is None:
                        continue
                    box = tuple(span[at] + patch[at % 2] for at in range(4))
                    seams[index][side] = max(seams[index].get(side, CROSS_SEAM),
                                             edges[side](box) + INSIDE_SLACK)

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
        # A shoulder is never in a set with anything else, whatever it looks like. A
        # cluster is held to one reach, the shortest any member can have, so a
        # shoulder in one would hand its outline's ceiling to a button meant to bloom
        # -- and on the GBA, whose `l` and `r` are drawn as round buttons in the same
        # diamond as A and B, that took all four down to 4.0pt.
        if (index in shoulders) != (other in shoulders):
            return False
        # Two shoulders, though, are a set whether or not their frames hug them: the
        # same button drawn twice, mirrored, along the same edge. The N64's landscape
        # pair came out 4.0pt and 3.0pt, which on rings that thin is one of them
        # visibly fatter than the other.
        return ((hugged(index) and hugged(other)
                 or index in shoulders and other in shoulders)
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
    arm_caps = {}     # cross -> how far each arm may reach out, once levelled
    arm_pieces = {}   # cross -> the rectangles its arms had before that
    hard = {}         # item -> the keep-outs that are a neighbour's glow
    glows = {}        # item -> the neighbouring halos behind those keep-outs
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

    def wearing(index):
        """The item's own frame as the mask has to cover it, at the least.

        Normally that is the frame itself. An item with a ring inside its artwork
        needs more: the ring runs right out to the artwork's edge, and the frame is
        drawn to the artwork's edge too -- a disc inscribed in the frame of a round
        button *is* the silhouette the halo starts from -- so a companion stopping
        at the frame would leave a rim of mask lying along light at full strength,
        which is the one thing no rectangle here may do. A couple of pixels past the
        artwork puts the frame's rim safely inside the companion, where nothing
        shows along it, and the companion's own rim out where the halo has already
        faded."""
        if index not in insides:
            return masks[index]
        art = arts[index]
        return union(masks[index], (art[0] - INSIDE_SLACK, art[1] - INSIDE_SLACK,
                                    art[2] + INSIDE_SLACK, art[3] + INSIDE_SLACK))

    def filled(index, alpha):
        """`alpha` with the ring the press vacates put back at full strength.

        Applied wherever a halo is finished off, the clipping included: a keep-out
        may lie over the button's own artwork, and a halo trimmed out of the ring
        there would leave the ghost edge showing under the pressed overlay -- the
        one thing this ring exists to cover."""
        inside = insides.get(index)
        return alpha if inside is None else ImageChops.lighter(alpha, inside)

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
            return filled(index, halo(art, reach, face=face, dist=distances(index)))
        near, top = crowd(index), round(reach * CROSS_REACH)
        reach = max(1, top if near is None else min(top, max(reach, near // 2)))
        alpha = halo(art, reach, face=0.0, dist=distances(index))
        local = (frames[index][0] - offset[0], frames[index][1] - offset[1],
                 frames[index][2] - offset[0], frames[index][3] - offset[1])
        ImageDraw.Draw(alpha).rectangle(
            (local[0], local[1], local[2] - 1, local[3] - 1), fill=0)
        return filled(index, arms(alpha, local, reach * CROSS_FADE,
                                  {side: mouth(art, local, side)
                                   for side in ('up', 'down', 'left', 'right')},
                                  caps=arm_caps.get(index)))

    def grown(index, reach, keepouts=(), ring=0, face=FACE_FRACTION):
        """A halo, the box it occupies, and the companion region that holds it.

        The region swallows the partner's frame, which is live beside the
        companion. Frames here hug their artwork, so a frame rim left outside
        would sit in the brightest part of the glow, where no amount of trimming
        would ever get it below a step.

        `ring` is a shorter reach that fits on every side, unioned back in after
        the clipping so the glow is unbroken around the artwork itself and only the
        bloom beyond it is one-sided.

        `face` is how much of a wash the button's own face gets; see `faces`.

        Two goes at it, because there are two ways for a halo to keep off a
        neighbour's glow and the gentler one usually works. First the halo as it wants
        to be, reaching round whatever is in its way. If no rectangle can carry that
        without covering something -- which is what a halo curling round a small button
        off one flank does -- then again with that flank stretched (`stretched`), so the
        glow stops flat against it and the box holding it is clean. The second way
        costs glow, all of it on the crowded side, and is only worth it where the first
        way leaves the halo uncarryable."""
        offset, asked = silhouettes[index][1], reach
        want = shape(index, reach, face)
        near = glows.get(index, ()) if keepouts else ()

        def made(bounds, loose=False):
            """The halo clipped to those keep-outs and the shape that carries it, or
            `None` where nothing carries it and `loose` isn't set."""
            alpha = want
            if bounds:
                alpha = clip(alpha, offset, bounds,
                             min(reach * CLIP_FADE, CLIP_REACH * ppp))
                if ring:
                    alpha = ImageChops.lighter(alpha, shape(index, ring, face))
                alpha = filled(index, alpha)
            found = shaping(alpha, loose)
            return None if found is None else dict(
                found, alpha=alpha, offset=offset, reach=reach, asked=asked,
                inside=insides.get(index))

        def shaping(alpha, loose):
            span = alpha.getbbox() or (0, 0, 0, 0)
            box = (span[0] + offset[0], span[1] + offset[1],
                   span[2] + offset[0], span[3] + offset[1])
            region = union(box, wearing(index))
            alone = {index: {'alpha': alpha, 'offset': offset, 'box': box}}
            pieces = carried(alpha, box, region, alone, loose)
            return None if pieces is None else {
                'box': box, 'pieces': pieces,
                'region': region if len(pieces) > 1 else union(region, pieces[0])}

        def carried(alpha, box, region, alone, loose):
            """The rectangles that will carry this halo: the smallest shape that fits
            it, or `None` where none of them does and `loose` isn't set."""

            def holds(piece):
                """Whether a rectangle holds any of this halo worth showing."""
                patch = intersect(piece, box)
                return patch is not None and alpha.crop(
                    (patch[0] - offset[0], patch[1] - offset[1],
                     patch[2] - offset[0], patch[3] - offset[1])
                    ).getextrema()[1] > EDGE_TOLERANCE

            def fits(pieces):
                """Whether a shape can carry this halo: every lit pixel of it inside the
                union -- what is left outside is a notch bitten out of the glow -- nothing
                of it along the union's boundary, and none of a neighbour's glow inside.
                The item's own frame is counted in, because DeltaCore puts that in the mask
                alongside the companion whenever the item is touched, and a rim buried in a
                sibling shows nothing.

                The neighbours matter here because a shape is not just a container: it is
                what a press puts on show. A disc is the tightest mask an even halo can
                have, but a one-sided one is not centred on its button, and a disc that
                takes its radius from the long side comes back over the neighbour that
                shortened the other -- so on the N64 the bloom A grew upwards would have
                lit the little `r` off its right flank. The box does not have that fault,
                so rejecting the disc costs a few pixels of mask rather than the glow."""
                stencil = Image.new('L', alpha.size, 0)
                for piece in pieces:
                    stencil = ImageChops.lighter(stencil,
                                                 solid(alpha.size, piece, offset))
                return (ImageChops.subtract(alpha, stencil).getextrema()[1]
                        <= EDGE_TOLERANCE
                        and brightest(alone, list(pieces) + [masks[index]])
                        <= EDGE_TOLERANCE
                        and all(revealed(entry, list(pieces)) <= EDGE_TOLERANCE
                                for entry in near))

            def clean(insets):
                """Whether the corners `notched` leaves out hold no glow.

                Two things ride on that. Nothing is missing from the mask that was worth
                drawing -- a corner cut out of a lit patch would read as a notch. And the
                item's own frame, which is live beside its companion whenever the item
                itself is touched, may stick out through the cut: the frame hugs the
                artwork, so if the corner is dark then the sliver of frame rim left on
                show out there has nothing along it either."""
                top, bottom, left, right = insets
                for x, wide in ((region[0], left), (region[2] - right, right)):
                    for y, high in ((region[1], top), (region[3] - bottom, bottom)):
                        if wide and high and holds((x, y, x + wide, y + high)):
                            return False
                return True

            # Two shapes, and whichever puts less of the skin into the mask wins, because
            # what a companion covers is what its neighbours lose.
            #
            # A disc is the tightest mask a round halo can have, and on a skin of round
            # buttons that is most of the packing. Centred on the button is the obvious
            # answer and it is only right for a halo that reaches the same distance all
            # round: one that blooms into the room on its left and dies out before the
            # neighbour on its right is not centred on its button, and a disc that is
            # loses half its radius to empty space on the crowded side -- reaching back
            # over the very neighbour that shortened it. So the centre of the glow is
            # offered as well, and the smaller disc wins. Either way `spanning` measures
            # from the centre being tried, so the disc holds the whole halo.
            #
            # The other is the box itself, cut in at each of its four sides as far as the
            # glow allows, leaving out the corners where two of those cuts meet
            # (`notched`). For an even halo that is an octagon and the disc is smaller.
            # For a one-sided one it is the better shape by a long way: the disc has to
            # take its radius from the longest reach and spends it in every direction,
            # while the cuts come in wherever the glow has faded out.
            # Measured to the glow the eye can see, not to the last pixel above zero.
            # A halo closes with a blur and its outermost few pixels are worth a level
            # or two out of 255 -- nothing a display shows, and the same nothing this
            # whole arrangement is allowed to cut through (`EDGE_TOLERANCE`). Sized to
            # those, a disc carries a few pixels of dead tail all the way round, and
            # on a diamond of buttons that tail is what puts it over the neighbour it
            # is trying to stay off.
            shapes = []
            if index in discs:
                lit = alpha.point(lambda level: level if level > EDGE_TOLERANCE else 0)
                middle = ((masks[index][0] + masks[index][2]) / 2.0,
                          (masks[index][1] + masks[index][3]) / 2.0)
                centre, radius = min(
                    ((spot, int(math.ceil(spanning(lit, offset, spot))) + 1)
                     for spot in (middle, ((box[0] + box[2]) / 2.0,
                                           (box[1] + box[3]) / 2.0))),
                    key=lambda pair: pair[1])
                shapes += [[round_box(centre, radius - trim)]
                           for trim in range(min(DISC_TRIMS, radius - 1) + 1)]

            deepest = (min(region[2] - region[0], region[3] - region[1]) - 1) // 2
            insets = [0, 0, 0, 0]
            for _ in range(2):          # a second pass: a deeper cut on one side can
                for side in range(4):   # let another go deeper still
                    for cut in ladder(deepest, 1):
                        if cut <= insets[side]:
                            break
                        trial = list(insets)
                        trial[side] = cut
                        if clean(trial):
                            insets = trial
                            break
            if any(insets):
                shapes += [notched(region, insets)]
            shapes += [[region]]

            pieces = min((shape for shape in shapes if fits(shape)), key=area,
                         default=None)

            # A staircase is the shape of last resort and of best fit at once. It is
            # the only one that can carry a lobe without covering the far side of the
            # button, so it is tried wherever the simple shapes can't hold the halo at
            # all, and wherever they hold it only by taking in most of the box. It
            # costs items in the skin, so it has to earn them.
            #
            # For a round button the staircase alone is no use: the halo is a disc and
            # a few bands across a disc are barely smaller than the box it sits in, and
            # on a diamond of four buttons the wide middle band reaches into both of
            # the diagonal neighbours at once. What that button wants is a ring and a
            # lobe -- a disc over the even part of the glow, and a staircase over the
            # bloom that carries on past it, tight to the one side it goes out on. The
            # disc's rim shows nothing, because the halo has faded to nothing by there
            # everywhere the staircase isn't sitting on top of it.
            #
            # This is what lets a face button in a diamond be bigger at all. Its
            # neighbours are half a gap away and that half is spent; the room is
            # outside the diamond, and a single disc big enough to reach it also
            # reaches back over the neighbours -- lighting them if their glow is there
            # already, and taking away the room for it if it isn't.
            flights = []
            # How much of its own disc the glow fills: a halo the clipper has been at
            # has room in there to give back, an even one never has.
            lopsided = index in discs and sum(
                alpha.histogram()[EDGE_TOLERANCE + 1:]) < LOBE_FULL * area(shapes[0])
            if pieces is None or lopsided \
                    or area(pieces) > STAIR_GAIN * area([region]):
                flights += [flight for cuts in STAIR_CUTS for axis in (0, 1)
                            for flight in [staircase(alpha, offset, region,
                                                     masks[index], cuts, axis)]
                            if flight is not None and len(flight) > 1]
                if index in discs:
                    whole = (shapes[0][0][2] - shapes[0][0][0]) // 2
                    least = int(math.ceil(max(masks[index][2] - middle[0],
                                              masks[index][3] - middle[1]))) + 1
                    for share in LOBE_SHARES:
                        radius = least + int(round((whole - least) * share))
                        if radius >= whole or radius <= least:
                            continue
                        inner = round_box(middle, radius)
                        rest = ImageChops.subtract(
                            alpha, solid(alpha.size, inner, offset))
                        edge = rest.point(
                            lambda level: 255 if level > EDGE_TOLERANCE else 0
                            ).getbbox()
                        if edge is None:
                            continue
                        lobe = (edge[0] + offset[0], edge[1] + offset[1],
                                edge[2] + offset[0], edge[3] + offset[1])
                        flights += [[inner, lobe]] + [
                            [inner] + flight
                            for cuts in STAIR_CUTS for axis in (0, 1)
                            for flight in [staircase(rest, offset, lobe,
                                                     None, cuts, axis)]
                            if flight is not None and len(flight) > 1]
                climbed = min((flight for flight in flights if fits(flight)),
                              key=area, default=None)
                if climbed is not None and (pieces is None
                                            or area(climbed)
                                            <= STAIR_GAIN * area(pieces)):
                    pieces = climbed
            return [region] if pieces is None and loose else pieces

        def flattened():
            """The keep-outs, with any that this halo would otherwise reach round
            stretched across the flank it sits on; see `stretched`."""
            reached = want.getbbox() or (0, 0, 0, 0)
            span = (reached[0] + offset[0], reached[1] + offset[1],
                    reached[2] + offset[0], reached[3] + offset[1])
            flanked = set(hard.get(index, ()))
            return [stretched(box, span, masks[index]) if box in flanked else box
                    for box in keepouts]

        return (made(keepouts) or made(flattened())
                or made(keepouts, loose=True))

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

        Except where the tilt's own ring is in there (`seams`): then the arm reaches
        back past the ring instead, so the rectangle's inner rim still lands on
        nothing lit. Sideways it is already clear -- the wedge outside the frame
        spreads wider than the mouth the ring ends at.

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
            box, frame = entry['box'], frames[index]
            seam = seams.get(index, {})
            deep = {side: seam.get(side, CROSS_SEAM)
                    for side in ('up', 'down', 'left', 'right')}
            pieces = {'up': (frame[0], box[1], frame[2], frame[1] + deep['up']),
                      'down': (frame[0], frame[3] - deep['down'], frame[2], box[3]),
                      'left': (box[0], frame[1], frame[0] + deep['left'], frame[3]),
                      'right': (frame[2] - deep['right'], frame[1], box[2], frame[3])}
            # An arm cut back to match its siblings (`evened`) keeps the rectangle it
            # had before the cut, which is the one already known to be clean. Pulling
            # a rectangle in is not free: a neighbour's glow that was buried inside
            # the old one can be left crossing the rim of the new one, and there is
            # nothing to gain here anyway -- the extra ground is glow this halo has
            # just given up, so it shows the same shell either way.
            kept = arm_pieces.get(index, {})
            banded[key] = {
                side: union(hugging(entry, piece, side), kept[side])
                if side in kept else hugging(entry, piece, side)
                for side, piece in pieces.items()
                if piece[2] > piece[0] and piece[3] > piece[1]
                and (side in kept or lit(entry, piece))}
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
        wide = {index: bare(index, ceiling[index]) for index in silhouettes}
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
    asked = {index: max(floor, min(ceiling[index], room(index)))
             for index in silhouettes}
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
        found = {index: [piece for other in silhouettes
                         for piece in fenced(index, other, reachable[other])]
                 for index in silhouettes}
        # Which of the keep-outs are somebody's glow, and whose. Kept here rather than
        # passed down because `grown` is handed one flat list of everything it has to
        # stay dark on, and a neighbour's glow is the one kind that has to be worked
        # round rather than merely faded before: widened where it would otherwise be
        # wrapped (`stretched`), and never covered by the rectangle that ends up
        # carrying this halo (`grown`).
        hard.clear()
        hard.update({index: [tuple(box) for box in boxes]
                     for index, boxes in found.items()})
        glows.clear()
        glows.update({index: [reachable[other] for other in silhouettes
                              if fenced(index, other, reachable[other])]
                      for index in silhouettes})
        return found

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
    # Unless the edge runs through the button itself. A shoulder button on these skins
    # is flush with it -- the NDS's `l` reaches x=0 -- and then there is no reach at
    # which a ring around it is dark at the edge, because the light that wraps its ends
    # is at the edge by the time it has gone anywhere. Asking anyway got the answer
    # `nothing fits`, which is how the shoulders ended up as the one thing on these
    # skins with no even collar at all: a crescent inside the button and a bloom past
    # it, next to face buttons wearing complete rings. Where the artwork already runs
    # off the display, light running off it too reads as the same thing, and the collar
    # is worth more than the fade.
    display = (0, 0, size[0], size[1])
    flush = {index for index in silhouettes
             if min(arts[index][0] - display[0], arts[index][1] - display[1],
                    display[2] - arts[index][2], display[3] - arts[index][3])
             <= FLUSH_SLACK}
    lines = {index: ([] if index in flush else [display])
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

    # And every halo that isn't bitten keeps the reach it settled on here as its ring,
    # because `expand` is about to try to grow it. A halo growing past what fits on
    # every side is the whole point of that pass -- the room a button has is rarely the
    # same in all four directions, and the N64's A had an inch of bare bezel above it
    # and a neighbour 38px to its left -- but it means the clipper starts biting into
    # a glow that was even a moment ago. Underneath it goes the even reach it had
    # before it grew, so what the eye sees is a whole ring at the button's edge with
    # the bloom past it one-sided, and never a rim with a piece missing.
    # Only those, though. A bitten halo the ladder above found no clear ring for is
    # hemmed in on every side at once, and handing it the reach it asked for as a ring
    # would restore, under every trim, the very glow the clipper had just taken off it:
    # the halo becomes unshrinkable and is dropped a few lines down for a step it can
    # no longer fix. The DS shoulders, whose bloom reaches out over the save and load
    # buttons, are exactly those halos.
    rings.update({index: asked[index] for index in silhouettes
                  if index not in rings and index not in bitten})

    # A round button's halo is even or it is nothing. Everything above is about
    # spending the room a button has, and a button never has the same room on every
    # side: the clipper's answer is to reach as far as each direction allows and fade
    # out where something is in the way, which is more glow but not a circle. On a
    # ring around a round button the eye reads that straight away -- wide and bright
    # on the open side, pinched and dim towards the neighbour -- and calls it a
    # defect rather than a bonus, however much light it adds. So a round button takes
    # the reach it can hold on every side at once (`rings`) and nothing is faded out
    # of it: what it shows is a circle, the same width the whole way round.
    #
    # The round ones and the shoulders. A shoulder used to keep the clipper so its
    # bloom could reach out over the save and load buttons beside it, but a bloom is
    # not what it takes now (`SHOULDER_POINTS`) -- and a ring thin enough to be an
    # outline is short enough to fit whole, so there is nothing left to trade. A d-pad
    # still keeps the clipper: it glows in the direction being pushed and is one-sided
    # by design. And a halo the ring ladder found nothing even for at all keeps it too
    # -- for those the choice is lopsided or unlit, and lopsided wins.
    even = {index for index in set(circles) | shoulders
            if index not in clipped and (index not in bitten or index in rings)}
    clips = {}                  # what the clipper would have been asked for
    for index in sorted(even & bitten):
        clips[index] = asked[index]
        asked[index] = rings[index]
    bitten -= even

    # No halo washes over the button's own face; see `FACE_FRACTION`. Kept as a
    # per-halo table because everything below asks for a halo by reach *and* face,
    # and a skin built with the wash turned back on has to go on working.
    faces = {}

    def at(index, reach):
        """A halo at a given reach, remembered: the search keeps asking for the
        same ones. Every halo goes through the clipper, since `expand` may grow one
        that fitted at first into a line it didn't reach before; one that meets
        nothing comes out of it untouched, because a keep-out it is already dark on
        is skipped."""
        if (index, reach) not in shaped:
            shaped[(index, reach)] = grown(
                index, reach, () if index in even else blocks(index),
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

    def strays(halos, positions, cap=EDGE_TOLERANCE):
        """The brightest foreign halo any of these presses would light.

        A press lights the button under your thumb and nothing else -- that rule is
        what bounds every reach here, and until a halo was allowed to be one-sided the
        geometry kept it on its own: half the gap each, and half a gap is too short to
        reach the neighbour. A bloom that runs past the halfway line has no such
        guarantee, so this is measured directly, on the same rectangles DeltaCore will
        build. See `revealed` for why the steps can't see it."""
        worst = 0
        for position in positions:
            live = None
            for index in halos:
                if index in shown(position):
                    continue
                if live is None:
                    live = regions(halos, position)
                worst = max(worst, revealed(halos[index], live))
                if worst > cap:
                    return worst
        return worst

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
                   default=0) <= EDGE_TOLERANCE \
                    and strays(trial, range(len(items))) <= EDGE_TOLERANCE:
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
                    touched = affected(trial, index, span)
                    # A shorter reach is a worse glow, so take the first that fits.
                    if blame(trial, index, touched) <= EDGE_TOLERANCE \
                            and strays(trial, touched) <= EDGE_TOLERANCE:
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
        if blamed in even:
            # A round halo hemmed in past the point of trimming, which is the one
            # case where being even costs a button its glow outright. Evenness is
            # worth a shorter reach, not a dead button: the halo goes back to the
            # clipper, fades out where the neighbour is, and keeps its even ring
            # underneath as far as that goes. Once each, so a halo the clipper
            # can't save either still ends up dropped below.
            if DEBUG:
                print('   declip', blamed, sorted(names[blamed]), 'blame',
                      blame(halos, blamed, bad, cap=255), 'bad', bad)
            even.discard(blamed)
            bitten.add(blamed)
            asked[blamed] = clips.get(blamed, asked[blamed])
            for key in [key for key in shaped if key[0] == blamed]:
                del shaped[key]
            halos = relax(sorted(halos))
            continue
        if DEBUG:
            print('   drops', blamed, sorted(names[blamed]), 'blame',
                  blame(halos, blamed, bad, cap=255), 'bad', bad,
                  {index: blame(halos, index, bad, cap=255) for index in halos})
        del halos[blamed]
        dropped.append(blamed)
        halos = relax(sorted(halos))

    def refresh(field, changed):
        """The fences brought up to date with halos that have just moved, and every
        shape chosen against the old ones forgotten.

        The clipper fades a halo out before its neighbours' rectangles and the shape
        search keeps its own rectangles off their glow -- both read the neighbours as
        they were when the fences were last measured. A halo that has just grown makes
        that reading wrong in the one direction that matters: the next halo along is
        fitted against a glow that has moved outwards, so it is allowed to reach where
        the light now is, and the step it takes is thrown out for a collision nobody
        had to have. Cheap to redo -- `fenced` is arithmetic -- and what it costs is
        the remembered shapes, which have to be rebuilt anyway to be worth anything."""
        stale = [index for index in glows
                 if any(fenced(index, other, field[other])
                        for other in changed if other in field and other != index)]
        for index in stale:
            fresh = [(other, fenced(index, other, field[other]))
                     for other in sorted(field)]
            glows[index] = [field[other] for other, boxes in fresh if boxes]
            keepouts[index] = [box for _, boxes in fresh for box in boxes]
            hard[index] = [tuple(box) for box in keepouts[index]]
            forget(index)

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
        wider.

        As one, but one at a time. Four halos in a diamond all reaching for the same
        step at once each grow towards the others, and a step every one of them could
        have taken is thrown out because two of them met in the middle -- which is why
        the face buttons stayed at the reach the ladder left them however much bare
        shell was outside the diamond. Taken in turn, each one is grown against its
        neighbours as they stand: the clipper fades it out before their glow, so the
        step goes on the sides where there is room and nowhere else, and the neighbour
        that follows is fenced by what this one has just become. The whole unit is
        still kept or dropped together, so they stay level."""
        given = {index: halos[index]['asked'] for index in halos}
        # A lopsided halo grows too, on its own. It is the one that most needs to --
        # what made it lopsided was a rectangle across its artwork, which says nothing
        # about the sides it is free on -- and it is out of every cluster by then, so
        # there is nobody to keep in step with. The N64's A had a C-pad arm over its
        # bottom third and an inch of empty bezel above it.
        units = teams(halos) + [(index,) for index in sorted(halos) if index in clipped]
        walled = set()
        for _ in range(ROUNDS):
            grew = False
            for unit in units:
                # The unit's own ceiling, not the reach asked for on the command line:
                # a shoulder's ring is thin on purpose, and this pass spends leftover
                # room, which is exactly what a shoulder has most of.
                top = min(ceiling[index] for index in unit) if unit else wanted
                if not unit or tuple(unit) in walled \
                        or max(given[index] for index in unit) >= top:
                    continue
                held = min(given[index] for index in unit)
                reach = min(top, max(held + 1, round(held / TRIMS[1])))
                # A step the unit can't hold whole is not the end of it: what it can
                # hold is somewhere between here and there, so the step is halved and
                # tried again, down to a single pixel. The ladder climbs in fifths and
                # a diamond of buttons has a few pixels of room, not a fifth of one --
                # without this the whole cluster stays at the rung below and the room
                # goes unused.
                stuck = True
                while stuck is not None and reach > held:
                    trial, stuck = dict(halos), None
                    for index in unit:
                        each = {**trial, index: at(index, reach)}
                        # The whole field, not just this halo's share: a longer reach
                        # moves the region as well, and a neighbour that was dark inside
                        # the old one may not be inside the new one.
                        touched = affected(each, index,
                                           union(halos[index]['region'],
                                                 each[index]['region']))
                        if max(step(each, touched).values(),
                               default=0) <= EDGE_TOLERANCE \
                                and strays(each, touched) <= EDGE_TOLERANCE:
                            trial = each
                            refresh(trial, [index])
                            continue
                        stuck = (index, each, touched)
                        break
                    if stuck is None:
                        halos, grew = trial, True
                        for index in unit:
                            given[index] = reach
                        break
                    refresh(halos, unit)    # the step is off; so are its fences
                    if DEBUG:
                        index, each, touched = stuck
                        found, culprit = max(
                            ((revealed(each[other], regions(each, position)),
                              (position, other))
                             for position in touched for other in each
                             if other not in shown(position)), default=(0, None))
                        print('   stuck', unit, held, '->', reach, 'on',
                              sorted(names[index]), 'step',
                              max(step(each, touched).values(), default=0),
                              'stray', found, culprit and
                              (sorted(names[culprit[0]]),
                               sorted(names[culprit[1]])))
                    reach = held + (reach - held) // 2
                if stuck is not None:
                    # Not even a pixel. Nothing that follows will make room for it
                    # either -- halos here only ever grow -- so the unit is done, and
                    # the rounds left are spent on the ones that can still move.
                    walled.add(tuple(unit))
            if not grew:
                break
        return halos

    def lengths(index, entry):
        """How far past its frame each of a d-pad's arms carries, in pixels, read off
        the rectangles the mask will really get."""
        frame, found = frames[index], {}
        for side, piece in bands(index, entry).items():
            found[side] = max(0, frame[1] - piece[1] if side == 'up' else
                              piece[3] - frame[3] if side == 'down' else
                              frame[0] - piece[0] if side == 'left' else
                              piece[2] - frame[2])
        return found

    def forget(index):
        """Everything remembered about one item's shape, dropped -- its arms are
        about to be cut back, so none of it describes the halo any more."""
        for key in [key for key in shaped
                    if key[0] == index or (key[0] == 'bare' and key[1] == index)]:
            del shaped[key]
        for key in [key for key in banded if key[0] == index]:
            del banded[key]

    def evened(halos):
        """A d-pad whose arms came out grossly unalike, cut back to its shortest.

        Reach is decided per side, against whatever that side runs into, and on most
        of these crosses the four sides run into much the same thing -- open shell --
        so they come out level on their own. The N64's portrait d-pad doesn't: the
        thumbstick's disc sits 49px above it and the up arm can never be more than
        that, while the other three had over 120px. Four arms of obviously different
        lengths read as a mistake even though each is as long as it can be, so the
        long ones give up their tips (`arms`, `reaching`).

        Only where it is really lopsided, and only when the short arm is still worth
        levelling to: cutting three good arms back to a stub would trade one flaw for
        a worse one, and levelling a cross whose arms differ by a few pixels would
        cost the d-pads their bloom for nothing the eye can see. Shorter is safe on
        its face -- less glow in less space -- but the rectangles come in with it, so
        the field is measured again all the same."""
        for index in sorted(halos):
            if index not in crosses:
                continue
            found = lengths(index, halos[index])
            if DEBUG:
                print('   arms', index, sorted(names[index]), found)
            if len(found) < 4:
                continue
            short, long = min(found.values()), max(found.values())
            if short < LEVEL_FLOOR * ppp or long < LEVEL_RATIO * short:
                continue
            arm_caps[index] = {side: short for side in found}
            arm_pieces[index] = dict(bands(index, halos[index]))
            forget(index)
            trial = {**halos, index: at(index, halos[index]['asked'])}
            if max(step(trial, range(len(items))).values(),
                   default=0) <= EDGE_TOLERANCE \
                    and strays(trial, range(len(items))) <= EDGE_TOLERANCE:
                if DEBUG:
                    print('   levels', index, sorted(names[index]), found,
                          '-> %dpx each' % short)
                halos = trial
            else:
                if DEBUG:
                    print('   uneven arms', index, 'step',
                          max(step(trial, range(len(items))).values(), default=0),
                          'stray', strays(trial, range(len(items)), cap=255))
                del arm_caps[index]
                del arm_pieces[index]
                forget(index)
        return halos

    halos = evened(level(expand(halos)))

    def held(entry, rect):
        """How much glow an entry holds inside one rectangle."""
        alpha, offset = entry['alpha'], entry['offset']
        box = (max(rect[0] - offset[0], 0), max(rect[1] - offset[1], 0),
               min(rect[2] - offset[0], alpha.width),
               min(rect[3] - offset[1], alpha.height))
        if box[2] <= box[0] or box[3] <= box[1]:
            return 0.0
        return mass(alpha.crop(box))

    def emptied(index):
        """Whether what the clipping left is too little to be worth showing, as a
        share of the same halo unclipped.

        A d-pad is judged an arm at a time and by its worst one, because that is how
        it is shown: a press lights one arm, and an arm the clip has emptied is a
        press with nothing to show for it while its neighbour lights up fully. Worse,
        what survives in a nearly-empty arm is whatever corner of it fell outside
        every foreign frame -- a bar of light off to one side of the button, which
        reads as a bug rather than as a glow. The N64's C buttons are that case:
        their four buttons are one item covering the whole cluster, glow inside the
        frame would light all four at once, and each arm is left with a sliver above
        or below the button and nothing at all to the sides."""
        entry = halos[index]
        whole = bare(index, entry['asked'], faces.get(index, FACE_FRACTION))
        if index not in crosses:
            return mass(entry['alpha']) < EMPTY_SHARE * max(1.0,
                                                            mass(whole['alpha']))
        # `bands` leaves out an arm with nothing lit in it, so four is what a d-pad
        # has when every direction glows and anything less is a dark one.
        pieces = bands(index, entry)
        shares = [held(entry, piece) / max(1.0, held(whole, piece))
                  for piece in pieces.values()]
        if DEBUG:
            print('   limbs', index, sorted(names[index]), len(pieces), 'arms',
                  ['%.0f%%' % (100.0 * share) for share in sorted(shares)])
        return len(pieces) < 4 or min(shares, default=0.0) < CROSS_EMPTY

    # A halo can come through the trimming intact and still hold nothing. A d-pad
    # only glows outside its own frame, and on a skin where every side of it is
    # somebody else's frame the clipping can take the whole strip. Calling that
    # unlit is more use than a companion that lights nothing.
    for index in sorted(halos):
        if emptied(index):
            if DEBUG:
                print('   culls', index, sorted(names[index]))
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
            if index in arm_caps:
                report.append('%d: arms levelled to %.1fpt each -- one direction had '
                              'far less room than the other three'
                              % (index, min(arm_caps[index].values()) / ppp))
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


def shell_level(base, entry):
    """How light the skin is under one halo, 0-255, or `None` where the halo has
    no bright part to measure.

    Measured under the band right against the artwork -- where the glow is at full
    strength, and where the contrast between it and the shell decides whether the
    press is seen at all. The ring inside the artwork doesn't count: what is under
    it is the button's own edge, which the pressed overlay covers, and a dark button
    on a pale shell would otherwise vote for the shell being dark."""
    core = entry['alpha'].point(lambda level: 255 if level > 200 else 0)
    if entry.get('inside') is not None:
        core = ImageChops.subtract(core, entry['inside'])
    span = core.getbbox()
    if span is None:
        return None
    offset = entry['offset']
    patch = base.convert('L').crop((span[0] + offset[0], span[1] + offset[1],
                                    span[2] + offset[0], span[3] + offset[1]))
    stencil = core.crop(span)
    lit = stencil.histogram()[255]
    if not lit or patch.size != stencil.size:
        return None
    return mass(ImageChops.multiply(patch, stencil)) / float(lit)


def suggest_color(levels, pale=PALE_LEVEL):
    """White, or `GLOW_WARM` if any of the buttons sits on a shell too pale for
    white to be seen against. `levels` is one `shell_level` per halo in the skin.

    Judged by the palest button rather than by the skin's average, because that is
    where the glow fails. The N64 is the case: a carbon shell almost throughout, and
    its A and B sit on a light grey plate -- so the average says white and the two
    buttons that most need to be seen are the two that vanish. A skin gets one
    colour (see `process`), so one button lost to it is enough to warm the lot.

    A glow is light, and light is only visible as a difference. On a dark shell
    white is the whole of that difference and nothing else looks as much like a
    lamp. On the N64's grey plate and the SNES's pale shell it isn't: the plate is
    already near white, so a white ring reads as paint on the plastic rather than
    as a button lighting up -- the N64's A and B looked unlit in the built skin
    even though the halo was there. Amber has somewhere to go on a pale shell,
    because a shell may be light but is hardly ever *warm*.

    A d-pad is left out of the vote. Its glow is four arms out on open shell rather
    than a ring around a button, so it is the one control that is nowhere near as
    hemmed in as the rest -- and on these skins it is also the one that sits on the
    darkest part of the shell, which is how the N64 came out white."""
    found = [level for level in levels if level is not None]
    if not found:
        return GLOW_COLOR
    if DEBUG:
        print('   shell %s/255 under the halos -- palest %.0f, %s'
              % ('/'.join('%.0f' % level for level in sorted(found)), max(found),
                 'so amber' if max(found) > pale else 'dark enough for white'))
    return GLOW_WARM if max(found) > pale else GLOW_COLOR


def pressed_name(asset):
    """DeltaCore's companion filename: `_pressed` before the extension."""
    stem, dot, extension = asset.rpartition('.')
    return '%s_pressed%s%s' % (stem, dot, extension) if dot else asset + '_pressed'
