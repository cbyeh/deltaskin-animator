#!/usr/bin/env python3
"""Add animated (per-button) assets to .deltaskin controller skins.

Delta commit 3e651d9 ("Supports animated controller skins"), with DeltaCore
633dfa8, made every item in info.json able to carry an

    "asset": { "name": "...", "width": ..., "height": ... }

dictionary. DeltaCore draws that image in its own UIImageView, sized `width` x
`height` mapping units and centred on the midpoint of the item's frame, and on
touch transforms it: buttons scale in by 2pt per side, d-pads tilt in 3D as if
pressed 3pt at the edge (plus 1pt into the screen overall).

Riley's own animated skins cut each button out of the layered source art, so
their base image has a hole where the button used to be. We only have the
flattened PNG, and can't punch holes in it because Delta's skin picker renders
the base image alone (see LoadControllerSkinImageOperation), so the button would
vanish from the thumbnail. So each overlay here is cut from the flattened image
and left sitting exactly where it came from:

* At rest it is a pixel-identical copy of what is underneath, and so invisible.
* When pressed, it needs to carry a band of surrounding background with it,
  because the original button is still in the base image and the band is what
  covers up its old edge as the overlay shrinks.

That band is what makes this delicate: it has to be wide enough to cover the
edge the button moved away from, but must not pick up any *other* artwork, or
that gets dragged along too. `skinlib.band_alpha` grows it out from the artwork
through smooth background only, stopping at any edge that isn't the button's
own, and fades out the last few points.

`--glow` adds a second kind of feedback on top: a soft white halo that blooms
around the button being held. That one rides on a DeltaCore feature nothing in
Delta exposes -- a `_pressed` companion to the skin's image -- and `glow.py`
explains what it takes to use it without disturbing a single touch target.

Input skins are never modified; rebuilt copies are written to the output
directory.

    python3 animate.py "My Skin.deltaskin"
    python3 animate.py *.deltaskin -o animated
    python3 animate.py *.deltaskin -o glowing --glow
"""

import argparse
import json
import math
import os
import shutil
import sys
import zipfile

from PIL import Image, ImageChops, ImageColor, ImageFilter

import glow
import press
from skinlib import (EDGE_THRESHOLDS, Skin, band_alpha, detect_interior, kind, label,
                     largest_regions, pixels_per_point, representations,
                     shape_interior, wall_map)

GLOW_TAG = 'GLOW'          # what a glowing build is renamed to, so both can install

# Colours worth naming that CSS doesn't have. Pillow understands every CSS name,
# and amber -- the one a pale shell actually wants -- isn't one of them.
GLOW_COLORS = {'amber': '#ffb300', 'warmwhite': '#fff3e0'}

MIN_SIDE = 30              # mapping units; below this a frame is a hint, not a button
MAX_AREA_FRACTION = 0.08   # skips full-screen items such as `fastForward`
SCREEN_OVERLAP = 0.5       # skips items mostly covering an emulator screen
MIN_ART_FRACTION = 0.35    # of the frame's area, else we only found a detail of it
DPAD_ART_FRACTION = 0.15   # d-pads are mostly gaps: four C buttons, or a thin cross
OVERLAP_TOLERANCE = 0.3    # of the smaller artwork's area

# What `find_art` records when it found no artwork and animated the touch frame's
# own shape instead. Such an item has nothing drawn for it in the shell, so it
# animates but never glows -- see the check in `rebuild_representation`.
FRAME_SHAPE = 'frame shape'

# How far out to look for a button's artwork, as a multiple of its frame size.
# Frames are often smaller than the art they sit on (and sometimes off-centre),
# so this grows until the artwork and its band fit with room to spare.
SEARCH_MARGINS = (0.75, 1.25, 2.0)

# Band widths to try, in points, narrowest first. A press moves the artwork's
# edge inwards by at most the press depth -- 2pt for a button, and about 4pt for
# the far corner of a tilted d-pad -- so a band a shade wider than that is all it
# takes to cover where the artwork was, and anything wider than that only makes
# the overlay bigger and the animation weaker. `band_for` measures the real
# transform rather than trusting these, and steps up only if it has to.
BAND_CANDIDATES = {False: (2.25, 3.0, 4.0, 5.5), True: (4.5, 5.5, 7.0, 9.0)}

# How far the band's outer edge takes to fade out. The band is background carried
# along with the button, and when the button moves so does the background in it --
# so wherever that background isn't flat, the band's own edge shows as a ghost of
# whatever it holds, displaced by the press. The N64's A button sits on a shiny grey
# plate and came out with a faint ring around it for exactly this reason. A longer
# fade spreads that difference out until it can't be seen; what it costs is opaque
# band, and the band only has to be opaque as far as the artwork's edge travels --
# about 2pt -- so there is room for a good deal more fade than there looks to be.
# `build_overlay` measures coverage on the real alpha, so a fade that did eat too
# much would show up as a wider band or more damping rather than as a ghost.
FEATHER_POINTS = {False: 3.0, True: 3.5}
PRESS_PAD = 32          # px of room around an overlay for a tilt to expand into

# A glowing button's overlay is cut to its artwork and nothing else, so its edge
# is one the eye sees -- the button against the light around it -- rather than one
# hidden in flat background. Half a pixel of softening is antialiasing, no more:
# any wider and the innermost ring of the halo would show through dimmed.
BARE_FEATHER = 0.5

# What counts as covered. A press may leave a hairline of the artwork uncovered
# where it runs right up against something else -- the N64's A button is tangent
# to the edge of its plate, so its band has nowhere to grow on that side -- as
# long as the gap stays thin and stays local. A gap that is thicker than a hair,
# or that rings the whole button, is a ghosted edge and is not accepted.
MAX_GHOST = 1           # px of erosion a gap may survive (about 3px wide)
MAX_GHOST_AREA = 0.02   # of the artwork's area

# Last resort for artwork whose band is fenced in before it is wide enough:
# padding the asset box by these fractions of its size damps the movement, which
# shrinks what a press can expose, at the cost of a less lively button.
DAMPING_STEPS = (0.2, 0.5, 1.0, 2.0)


def rect(frame):
    return (frame['x'], frame['y'],
            frame['x'] + frame['width'], frame['y'] + frame['height'])


def contains(outer, inner):
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def overlap(a, b):
    if a is None or b is None:
        return 0
    dx = min(a[2], b[2]) - max(a[0], b[0])
    dy = min(a[3], b[3]) - max(a[1], b[1])
    return dx * dy if dx > 0 and dy > 0 else 0


def area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def base_reject(item, rep):
    """Reasons an item can never be animated, independent of the artwork."""
    item_kind = kind(item)
    if item_kind in ('touchScreen', 'thumbstick'):
        return item_kind                      # thumbsticks DeltaCore animates itself
    if isinstance(item['inputs'], list) and len(item['inputs']) > 1:
        return 'combo zone'

    frame = item['frame']
    mapping = rep['mappingSize']
    if (frame['width'] * frame['height']) / (mapping['width'] * mapping['height']) > MAX_AREA_FRACTION:
        return 'too large'
    if min(frame['width'], frame['height']) < MIN_SIDE:
        return 'too small (%gpt)' % round(min(frame['width'], frame['height']) / 3, 1)

    for screen in rep.get('screens', []):
        output = screen.get('outputFrame')
        if output and overlap(rect(frame), rect(output)) > SCREEN_OVERLAP * area(rect(frame)):
            return 'sits on screen'
    return None


def padded_crop(base, box):
    """Crop `base` over `box`, which may hang off the image, plus a mask of the
    part that does. Off-image area is transparent and treated as a hard edge, so
    the artwork search neither leaks into it nor grows a band over it."""
    crop = Image.new('RGBA', (box[2] - box[0], box[3] - box[1]))
    inner = (max(box[0], 0), max(box[1], 0), min(box[2], base.width), min(box[3], base.height))
    outside = Image.new('L', crop.size, 255)
    if inner[2] > inner[0] and inner[3] > inner[1]:
        crop.paste(base.crop(inner), (inner[0] - box[0], inner[1] - box[1]))
        outside.paste(Image.new('L', (inner[2] - inner[0], inner[3] - inner[1]), 0),
                      (inner[0] - box[0], inner[1] - box[1]))
    return crop, outside


def search_area(base, frame, margin):
    """A region of the skin centred on `frame`, `margin` frame-widths wider on
    each side, along with where the frame sits in it and which of its sides hang
    off the skin (artwork is allowed to run off those)."""
    centre = (frame['x'] + frame['width'] / 2.0, frame['y'] + frame['height'] / 2.0)
    half_w, half_h = frame['width'] * (0.5 + margin), frame['height'] * (0.5 + margin)
    box = (int(centre[0] - half_w), int(centre[1] - half_h),
           int(centre[0] + half_w) + 1, int(centre[1] + half_h) + 1)
    crop, outside = padded_crop(base, box)
    return {
        'box': box, 'crop': crop, 'outside': outside,
        'frame_box': (frame['x'] - box[0], frame['y'] - box[1],
                      frame['x'] + frame['width'] - box[0], frame['y'] + frame['height'] - box[1]),
        'open_sides': tuple(side for side, off in (
            ('left', box[0] < 0), ('top', box[1] < 0),
            ('right', box[2] > base.width), ('bottom', box[3] > base.height)) if off),
    }


def overlay_for(view, walls, interior, pixels, ppp, is_dpad, source):
    """A candidate detection, measured with the widest band it might end up using
    so that `contained` stays true of the overlay actually built later."""
    widest = max(1, round(BAND_CANDIDATES[is_dpad][-1] * ppp))
    feather = max(1, round(FEATHER_POINTS[is_dpad] * ppp))
    alpha, _ = band_alpha(view['crop'], interior, walls, ppp, widest, feather)
    span = alpha.getbbox()
    if span is None:
        return None
    crop, open_sides = view['crop'], view['open_sides']
    return {
        'view': view, 'walls': walls, 'interior': interior,
        'source': source, 'pixels': pixels,
        # Room to spare on every side means the band ended on its own terms
        # rather than being cut off by the edge of the search area.
        'contained': ((span[0] > 0 or 'left' in open_sides)
                      and (span[1] > 0 or 'top' in open_sides)
                      and (span[2] < crop.width or 'right' in open_sides)
                      and (span[3] < crop.height or 'bottom' in open_sides)),
        'art': tuple(v + view['box'][i % 2] for i, v in enumerate(interior.getbbox())),
    }


def find_art(base, item, ppp, whole=False):
    """Locate an item's artwork.

    Returns a dict with the alpha covering the artwork and its band, where in the
    image that alpha sits, the artwork's own bounds, and how it was found. Widens
    the search area until the band ends on its own terms rather than being cut off
    by the edge of that area, and relaxes the edge threshold until the artwork is
    a decent fraction of the item's frame. Failing both, falls back to the frame's
    shape, so the button animates regardless.

    `whole` asks for the button rather than any convincing part of it; see
    `reaches_frame`."""
    frame = item['frame']
    is_dpad = kind(item) == 'dPad'
    enough = (DPAD_ART_FRACTION if is_dpad else MIN_ART_FRACTION) * frame['width'] * frame['height']
    best = None

    def reaches_frame(found):
        """Whether what was found is the button or a detail inside it.

        The search stops at the first edge it can't cross, and the strictest
        threshold finds that edge wherever the artwork has one of its own: on the
        N64's portrait shoulders it is the groove around the engraved *L*, so what
        came back was the 148x68 recess out of a 190x100 button -- which clears
        `MIN_ART_FRACTION` by itself, and the looser threshold that would have
        found the whole 184x117 plate was never tried.

        An overlay of the recess is only a slightly smaller animation. A halo
        grown from it is an outline drawn *inside* the button, hugging the recess
        with the whole bezel dark outside it, which reads as a mistake rather than
        as a glow. So an item whose silhouette becomes a halo keeps relaxing until
        what it found reaches out to its touch frame -- the same test
        `glow.visible` applies before it trusts that frame to stand in for the
        button's visible edge."""
        cap = glow.RIM_SHARE * min(frame['width'], frame['height'])
        box = found['art']
        return all(inset <= cap for inset in (
            box[0] - frame['x'], box[1] - frame['y'],
            frame['x'] + frame['width'] - box[2],
            frame['y'] + frame['height'] - box[3]))

    for margin in SEARCH_MARGINS:
        view = search_area(base, frame, margin)
        for threshold in EDGE_THRESHOLDS:
            walls = wall_map(view['crop'], threshold, view['outside'])
            interior, pixels = detect_interior(walls, view['frame_box'], view['open_sides'])
            if interior is None:
                continue
            found = overlay_for(view, walls, interior, pixels, ppp, is_dpad, 'detected')
            if found is None:
                continue
            if best is None or (found['contained'], found['pixels']) > (best['contained'], best['pixels']):
                best = found
            if found['contained'] and pixels >= enough \
                    and (not whole or reaches_frame(found)):
                return found

    # Nothing convincing: animate the frame's shape instead.
    view = search_area(base, frame, SEARCH_MARGINS[0])
    walls = wall_map(view['crop'], EDGE_THRESHOLDS[0], view['outside'])
    interior = shape_interior(view['crop'].size, view['frame_box'])
    pixels = sum(1 for value in interior.getdata() if value)
    shaped = overlay_for(view, walls, interior, pixels, ppp, is_dpad, FRAME_SHAPE)
    if shaped is not None and (best is None or not best['contained']
                               or best['pixels'] < enough):
        return shaped
    return best


def exposure(alpha, art_mask, offset, box, ppp, is_dpad):
    """The worst fraction of the artwork a press leaves uncovered.

    Runs the artwork's own shape through DeltaCore's transform -- every d-pad
    direction, not just one -- and asks whether the overlay, once moved, still
    covers everywhere the artwork used to be. Anywhere it doesn't, the base
    image's copy of the button shows through as a ghosted edge. This is the
    measurement the band width is chosen to satisfy."""
    width, height = box[2] - box[0], box[3] - box[1]
    canvas = (width + 2 * PRESS_PAD, height + 2 * PRESS_PAD)
    at = (offset[0] - box[0] + PRESS_PAD, offset[1] - box[1] + PRESS_PAD)

    rest = Image.new('L', canvas)
    rest.paste(alpha, at)
    art = Image.new('L', canvas)
    art.paste(art_mask, at)
    art = ImageChops.multiply(art, rest).point(lambda v: 255 if v >= 250 else 0)
    total = art.histogram()[255]
    if not total:
        return 0.0

    source = [(PRESS_PAD, PRESS_PAD), (PRESS_PAD + width, PRESS_PAD),
              (PRESS_PAD + width, PRESS_PAD + height), (PRESS_PAD, PRESS_PAD + height)]
    centre = (PRESS_PAD + width / 2.0, PRESS_PAD + height / 2.0)

    # Area and thickness are tracked separately: the state that leaves the most
    # uncovered is not always the one that leaves the thickest gap, and it is the
    # thickest gap that gets noticed.
    worst_area, worst_thickness = 0.0, 0
    for state in press.states(is_dpad):
        quad = press.quad(width / ppp, height / ppp, state)
        destination = [(centre[0] + x * ppp, centre[1] + y * ppp) for x, y in quad]
        coefficients = press.perspective_coefficients(destination, source)
        pressed = rest.transform(canvas, Image.PERSPECTIVE, coefficients, Image.BILINEAR)
        # Resampling softens the overlay's edge, so allow the cover to fall a
        # pixel short of where it lands: less than that is invisible anyway.
        covered = pressed.point(lambda v: 255 if v >= 200 else 0)
        gap = ImageChops.subtract(art, covered.filter(ImageFilter.MaxFilter(3)))
        worst_area = max(worst_area, gap.histogram()[255] / total)
        worst_thickness = max(worst_thickness, thickness(gap))
    return worst_area, worst_thickness


def thickness(mask):
    """Roughly half the width of the widest part of `mask`, in pixels.

    Area alone doesn't say whether a gap will be seen: a hairline where a button
    happens to touch something else is invisible, while a gap of the same area
    spread as an even ring around the button is the ghosted edge we are trying to
    avoid. Eroding tells the two apart."""
    for radius in range(1, MAX_GHOST + 2):
        if mask.filter(ImageFilter.MinFilter(2 * radius + 1)).getbbox() is None:
            return radius - 1
    return MAX_GHOST + 1


def vacated(alpha, art_mask, offset, box, ppp, is_dpad):
    """Everywhere a press slides the overlay off, over all press states, in the
    overlay's own coordinates -- and where that canvas sits in the image.

    The counterpart to `exposure`: the same transform, kept rather than measured.
    A glowing button's overlay carries no band, so this ring is where the base
    image's copy of the button would show through, and the halo fills it at full
    strength instead (`glow.build`). Grown by a pixel, since the overlay's own edge
    is resampled and lands a shade inside where the transform says.

    A d-pad also gets the ring per press state, under `states`: its glow is handed
    out an arm at a time, so `glow.build` has to know which arm covers what -- which
    it works out by zone, being the one that knows where the zones are. A tilt turns
    out to uncover only the tip of the arm being pushed, which is why this works at
    all: what a diagonal uncovers falls to the two arms it lights, one piece each."""
    width, height = box[2] - box[0], box[3] - box[1]
    canvas = (width + 2 * PRESS_PAD, height + 2 * PRESS_PAD)
    at = (offset[0] - box[0] + PRESS_PAD, offset[1] - box[1] + PRESS_PAD)
    origin = (box[0] - PRESS_PAD, box[1] - PRESS_PAD)

    rest = Image.new('L', canvas)
    rest.paste(alpha, at)
    art = Image.new('L', canvas)
    art.paste(art_mask, at)
    art = ImageChops.multiply(art, rest).point(lambda v: 255 if v >= 250 else 0)

    source = [(PRESS_PAD, PRESS_PAD), (PRESS_PAD + width, PRESS_PAD),
              (PRESS_PAD + width, PRESS_PAD + height), (PRESS_PAD, PRESS_PAD + height)]
    centre = (PRESS_PAD + width / 2.0, PRESS_PAD + height / 2.0)

    gaps, states = Image.new('L', canvas), {}
    for state in press.states(is_dpad):
        quad = press.quad(width / ppp, height / ppp, state)
        destination = [(centre[0] + x * ppp, centre[1] + y * ppp) for x, y in quad]
        coefficients = press.perspective_coefficients(destination, source)
        pressed = rest.transform(canvas, Image.PERSPECTIVE, coefficients, Image.BILINEAR)
        covered = pressed.point(lambda v: 255 if v >= 200 else 0)
        gap = ImageChops.subtract(art, covered).filter(ImageFilter.MaxFilter(3))
        gaps = ImageChops.lighter(gaps, gap)
        if is_dpad and state != 'centre':
            states[state] = gap
    return {'mask': gaps, 'offset': origin, 'states': states or None}


def bare_overlay(mark, centre, ppp, is_dpad):
    """An overlay cut to the artwork alone, for a button whose halo will cover the
    edge it leaves behind.

    No band, so nothing of the button's surroundings is carried over the halo and
    the whole ring shows; and no band means nothing scaling the transform down
    either, so the button moves the full press depth. The boundary is softened by a
    fraction of a pixel because it is now an edge the eye sees, between the button
    and the light around it, rather than one hidden in flat background."""
    alpha = mark['mask'].filter(ImageFilter.GaussianBlur(BARE_FEATHER))
    offset = mark['origin']
    span = alpha.getbbox()
    box = asset_box(tuple(value + offset[index % 2]
                          for index, value in enumerate(span)), centre)
    built = {'alpha': alpha, 'art_mask': mark['mask'], 'offset': offset, 'box': box,
             'band': 0.0, 'damping': 0, 'lit': True,
             'exposed': exposure(alpha, mark['mask'], offset, box, ppp, is_dpad)}
    built['travel'] = travel(built, ppp, is_dpad)
    built['vacated'] = vacated(alpha, mark['mask'], offset, box, ppp, is_dpad)
    return built


def build_overlay(entry, ppp, is_dpad, centre):
    """Settle on a band width and an asset box for a detected item.

    Tries each band in turn and stops at the first that covers the artwork under
    every press, so the overlay stays as small as it can and the button moves as
    much as Riley's do. If even the widest band is fenced in too tightly to cover
    -- the N64's A button, hemmed in by the edge of the plate it sits on -- the
    asset box is padded out instead, which damps the movement until what is left
    is small enough to hide. Less animation, but no ghost either way."""
    feather = max(1, round(FEATHER_POINTS[is_dpad] * ppp))
    offset = (entry['view']['box'][0], entry['view']['box'][1])
    best = None

    for points in BAND_CANDIDATES[is_dpad]:
        alpha, art_mask = band_alpha(entry['view']['crop'], entry['interior'],
                                     entry['walls'], ppp, max(1, round(points * ppp)), feather)
        span = alpha.getbbox()
        if span is None:
            continue
        tight = asset_box(tuple(v + offset[i % 2] for i, v in enumerate(span)), centre)

        for damping in (0,) + DAMPING_STEPS:
            pad = (round(damping * (tight[2] - tight[0]) / 2.0),
                   round(damping * (tight[3] - tight[1]) / 2.0))
            box = (tight[0] - pad[0], tight[1] - pad[1], tight[2] + pad[0], tight[3] + pad[1])
            built = {'alpha': alpha, 'art_mask': art_mask, 'offset': offset, 'box': box,
                     'band': points, 'damping': damping,
                     'exposed': exposure(alpha, art_mask, offset, box, ppp, is_dpad)}
            built['travel'] = travel(built, ppp, is_dpad)
            if best is None or preferred(built, best):
                best = built
            if covered(built['exposed']):
                break               # damping only costs movement from here on

        # A band this narrow covering on its own is as good as it gets: every
        # wider one carries more and moves less.
        if best is not None and covered(best['exposed']) and best['damping'] == 0:
            break
    return best


def covered(exposed):
    fraction, thick = exposed
    return thick <= MAX_GHOST and fraction <= MAX_GHOST_AREA


def preferred(candidate, incumbent):
    """Covering beats not covering; then more movement; then less exposure."""
    if covered(candidate['exposed']) != covered(incumbent['exposed']):
        return covered(candidate['exposed'])
    if covered(candidate['exposed']):
        return candidate['travel'][0] > incumbent['travel'][0]
    return candidate['exposed'] < incumbent['exposed']


def travel(built, ppp, is_dpad):
    """Points the artwork's edge moves when pressed, and what fraction that is of
    the movement Riley's own skins get. Anything the overlay carries beyond the
    artwork itself scales the movement down, so this is the honest measure of how
    responsive a button will look."""
    depth = press.DPAD_EDGE_DEPTH if is_dpad else press.BUTTON_DEPTH
    span = built['art_mask'].getbbox()
    if span is None:
        return 0.0, 0.0
    offset, box = built['offset'], built['box']
    art = tuple(v + offset[i % 2] for i, v in enumerate(span))
    centre = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
    reach = max(centre[0] - art[0], art[2] - centre[0],
                centre[1] - art[1], art[3] - centre[1])
    half = max(box[2] - box[0], box[3] - box[1]) / 2.0
    moved = depth * reach / half
    return moved, moved / depth


def asset_box(span, centre):
    """Smallest whole-pixel box symmetric about `centre` that contains `span`.

    Symmetry is not optional: DeltaCore centres the overlay on the midpoint of
    the item's frame, so that midpoint is the only place the box can be centred
    on and still land back where the pixels were cut from."""
    def half(need, middle):
        # A half-pixel centre needs a half-pixel half-extent to land on whole pixels.
        if middle == int(middle):
            return math.ceil(need)
        return math.ceil(need - 0.5) + 0.5

    half_w = half(max(centre[0] - span[0], span[2] - centre[0]), centre[0])
    half_h = half(max(centre[1] - span[1], span[3] - centre[1]), centre[1])
    return (int(centre[0] - half_w), int(centre[1] - half_h),
            int(centre[0] + half_w), int(centre[1] + half_h))


def process(skin, out_dir, verbose=True, animating=True, glowing=False,
            points=glow.GLOW_POINTS, opacity=glow.GLOW_OPACITY,
            color=None, tag=GLOW_TAG, sharing=glow.GLOW_SHARE,
            inputs=glow.GLOW_INPUTS):
    """Rebuild one skin into `out_dir`. `color` of `None` picks white or amber
    per skin, by what the shell under its halos turns out to be."""
    info = json.loads(json.dumps(skin.info))
    total = glows = extras = 0
    fields = {}         # asset filename -> (base image, accumulated glow alpha)
    shells = []         # how light the skin is under each halo; see suggest_color

    for key, rep in representations(info):
        assets = rep['assets']
        if len(set(assets.values())) > 1 and verbose:
            print('     ! %s draws from %d different images; overlays are cut from %s'
                  % ('/'.join(key), len(set(assets.values())), list(assets)[0]))
        base = skin.image(list(assets.values())[0])
        ppp = pixels_per_point(key, base)
        if verbose:
            print('  %s  %dx%d' % ('/'.join(key), base.width, base.height))

        found, rejected = [], []
        for index, item in enumerate(rep['items']):
            reason = base_reject(item, rep)
            if reason:
                rejected.append((index, item, reason))
                continue
            entry = find_art(base, item, ppp,
                             whole=glowing and glow.worth_glowing(item, inputs))
            if entry is None:
                rejected.append((index, item, 'no artwork found'))
                continue
            entry.update(index=index, item=item)
            found.append(entry)

        # One overlay can only show one item's artwork, so items that resolve to
        # the same art can't both animate. A d-pad keeps it: it is one piece of
        # art shared by four or more inputs, and its tilt is the whole point (the
        # N64's Z sits inside the C cluster, so the cluster tilts and Z rides
        # along with it). Failing that a frame sitting inside another's gives way,
        # and failing that the item with the larger artwork does, being the more
        # likely to have caught something that isn't its own.
        # Resolve one at a time, since dropping one can settle others.
        while True:
            clash = None
            for i, a in enumerate(found):
                for b in found[i + 1:]:
                    if overlap(a['art'], b['art']) <= OVERLAP_TOLERANCE * min(area(a['art']), area(b['art'])):
                        continue
                    a_moves, b_moves = kind(a['item']) != 'button', kind(b['item']) != 'button'
                    if a_moves != b_moves:
                        loser, winner = (b, a) if a_moves else (a, b)
                        clash = (loser, 'artwork is item %d\'s' % winner['index'])
                    elif contains(rect(a['item']['frame']), rect(b['item']['frame'])):
                        clash = (b, 'artwork is item %d\'s' % a['index'])
                    elif contains(rect(b['item']['frame']), rect(a['item']['frame'])):
                        clash = (a, 'artwork is item %d\'s' % b['index'])
                    else:
                        inner, outer = sorted((a, b), key=lambda e: area(e['art']))
                        clash = (outer, 'shares artwork with item %d' % inner['index'])
                    break
                if clash:
                    break
            if not clash:
                break
            loser, reason = clash
            found.remove(loser)
            rejected.append((loser['index'], loser['item'], reason))

        to_pixels = (base.width / rep['mappingSize']['width'],
                     base.height / rep['mappingSize']['height'])
        used, sources, plain, rings = set(), {}, [], {}
        overlays = {}       # index -> the overlay decided on, written out below
        summary, notes = None, []
        for entry in sorted(found, key=lambda e: e['index']):
            item = entry['item']
            frame = item['frame']
            centre = (frame['x'] + frame['width'] / 2.0, frame['y'] + frame['height'] / 2.0)
            is_dpad = kind(item) == 'dPad'
            # A halo says "this is the button you pressed", so it needs a button to
            # say it about. An item that fell back to its frame's shape has no
            # artwork in the shell at all -- it is a bare touch target, and the N64
            # skin puts one for `r` down beside the A button, on top of plain shell,
            # while the R trigger it duplicates sits up at the top edge with the
            # artwork. Lighting both means one press blooming in two places, the
            # second of them a square of light over nothing. It still animates.
            lit = (glowing and glow.worth_glowing(item, inputs)
                   and entry['source'] != FRAME_SHAPE)
            mark = None
            if not lit:
                if glowing:
                    plain.append(label(item))
            else:
                # The button's own face, not the artwork the overlay moves: that
                # one takes the surrounding shadow with it, which would start the
                # halo a dozen pixels out into the shell and cost it that much
                # reach for nothing. `glow.visible` grows it back out to the
                # button's edge, which is where the halo belongs.
                interior = largest_regions(entry['interior'])
                at = (entry['view']['box'][0], entry['view']['box'][1])
                sources[entry['index']] = (interior, at)
                # The same silhouette the halo will start from, which is what the
                # overlay is cut to so that none of it lands on the halo. A d-pad
                # comes along: a tilt only uncovers the tip of the arm being pushed
                # -- the far side of the cross barely moves -- so the ring left
                # behind falls inside the one direction whose glow is lit, and that
                # glow can cover it the same way a button's does.
                mark = glow.footprint(interior, at,
                                      glow.scaled(glow.frame_box(item), to_pixels),
                                      4, is_dpad, glow.shoulder(item))

            built = None
            if animating:
                built = (bare_overlay(mark, centre, ppp, is_dpad) if mark is not None
                         else build_overlay(entry, ppp, is_dpad, centre))
            if animating and built is None:
                rejected.append((entry['index'], item, 'no artwork found'))
                sources.pop(entry['index'], None)   # nothing to animate, nothing to light
                continue
            if built is not None and 'vacated' in built:
                rings[entry['index']] = built['vacated']
            if not animating:
                continue
            overlays[entry['index']] = (entry, built)

        if glowing and sources:
            notes = []
            # A bandless overlay is only safe where the halo really turns up to cover
            # the edge it leaves behind, and whether it does isn't known until the
            # halos are packed: a ring is light inside the artwork, and an item whose
            # artwork lies under a neighbour's mask region has that region's rim
            # running through it, which is a seam no trimming can fix -- so the halo
            # is dropped instead. Those items go back to carrying a band, which asks
            # nothing of the glow, and the packing runs again: without a ring to cut,
            # such an item usually keeps a halo after all, and if it still doesn't,
            # the band is what its press needed anyway.
            while True:
                notes = []
                field, companions, halos = glow.build(rep, base.size, sources, points,
                                                      ppp, notes, sharing, rings)
                banding = [index for index in sorted(rings)
                           if index not in halos and index in overlays]
                if not banding or not animating:
                    break
                for index in banding:
                    entry = overlays[index][0]
                    frame = entry['item']['frame']
                    overlays[index] = (entry, build_overlay(
                        entry, ppp, kind(entry['item']) == 'dPad',
                        (frame['x'] + frame['width'] / 2.0,
                         frame['y'] + frame['height'] / 2.0)))
                    rings.pop(index)
            # Must be appended only after `build`, which indexes the real items.
            rep['items'].extend(companions)
            glows += len(halos)
            extras += len(companions)
            shells += [glow.shell_level(base, entry)
                       for index, entry in sorted(halos.items())
                       if not glow.directional(rep['items'][index])]

            asset = list(assets.values())[0]
            if asset in fields and verbose:
                print('     ! %s is shared with another representation; its glows '
                      'are merged' % asset)
            # Every image the representation can draw needs a `_pressed` companion
            # of its own: DeltaCore looks one up beside whichever asset size it
            # picked, and finding none just means no glow. In these skins all three
            # sizes are the same file; where they differ the field is scaled to fit.
            for name in dict.fromkeys(assets.values()):
                image = base if name == asset else skin.image(name)
                alpha = (field if image.size == field.size
                         else field.resize(image.size, Image.LANCZOS))
                existing = fields.get(name)
                fields[name] = (image, ImageChops.lighter(existing[1], alpha)
                                if existing else alpha)

            summary = (len(halos), len(companions))

        for index, (entry, built) in sorted(overlays.items()):
            item, frame = entry['item'], entry['item']['frame']
            alpha, offset, box = built['alpha'], built['offset'], built['box']

            overlay, _ = padded_crop(base, box)
            cut = Image.new('L', overlay.size)
            cut.paste(alpha, (offset[0] - box[0], offset[1] - box[1]))
            overlay.putalpha(cut)

            stem = 'anim_%s_%s' % (key[2], label(item))
            name, suffix = stem + '.png', 2
            while name in used:
                name, suffix = '%s_%d.png' % (stem, suffix), suffix + 1
            used.add(name)

            overlay.save(os.path.join(out_dir, name), optimize=True)
            item['asset'] = {'name': name, 'width': box[2] - box[0], 'height': box[3] - box[1]}
            for existing in [k for k in list(item) if k != 'asset']:
                item[existing] = item.pop(existing)     # keep `asset` first, as Riley's skins do
            total += 1

            if verbose:
                art = entry['art']
                moved, fraction = built['travel']
                extras_note = ['%s' % entry['source'],
                               'no band, the halo covers the edge' if built.get('lit')
                               else 'band %.2fpt' % built['band']]
                if built['damping']:
                    extras_note.append('damped %.0f%%' % (100 * built['damping']))
                if not built.get('lit') and not covered(built['exposed']):
                    extras_note.append('EXPOSES %.1f%% of artwork, %dpx thick'
                                       % (100 * built['exposed'][0],
                                          2 * built['exposed'][1] + 1))
                print('     + %-18s frame %dx%d  art %dx%d  asset %dx%d  '
                      'moves %.2fpt (%.0f%%)  [%s]'
                      % (label(item), frame['width'], frame['height'],
                         art[2] - art[0], art[3] - art[1],
                         box[2] - box[0], box[3] - box[1], moved, 100 * fraction,
                         ', '.join(extras_note)))
        if verbose:
            for index, item, reason in sorted(rejected, key=lambda entry: entry[0]):
                print('     - %-18s %s' % (label(item), reason))
            if summary is not None:
                print('     glow %.1fpt around %d items, %d mask companions%s'
                      % ((points,) + summary +
                         ('  (no glow: %s)' % ', '.join(plain) if plain else '',)))
                for note in notes:
                    index, text = note.split(': ', 1)
                    print('     ~ %-18s %s' % (label(rep['items'][int(index)]), text))

    for name in skin.names():
        if name != 'info.json':
            with open(os.path.join(out_dir, os.path.basename(name)), 'wb') as file:
                file.write(skin.read(name))
    # One colour for the whole skin, decided from the shell it will be laid over
    # unless it was asked for: a skin carries one `glow` record and shows one name,
    # and Delta picks whichever asset size fits, so two representations of the same
    # skin glowing different colours would be the same skin lighting differently in
    # portrait and landscape.
    if color is None:
        color = glow.suggest_color(shells)
        if verbose and fields:
            print('  glow #%02x%02x%02x -- %s' % (
                tuple(color) + ('white, which the shell is dark enough to show'
                                if tuple(color) == glow.GLOW_COLOR
                                else 'the shell is too pale for white',)))
    for asset, (base, field) in fields.items():
        glow.apply(base, field, opacity, color).save(
            os.path.join(out_dir, os.path.basename(glow.pressed_name(asset))),
            optimize=True)
    if glowing:
        info['name'] = '%s [%s]' % (info['name'], tag)
        info['identifier'] = '%s.%s' % (info['identifier'], tag.lower())
        # What the halo was made of, for verify.py to check the pressed images
        # against. DeltaCore reads the keys it knows and ignores the rest.
        info['glow'] = {'color': '#%02x%02x%02x' % tuple(color),
                        'points': points, 'opacity': opacity}
    with open(os.path.join(out_dir, 'info.json'), 'w') as file:
        json.dump(info, file, indent=2)
        file.write('\n')
    return {'animated': total, 'glowing': glows, 'companions': extras}


def archive(out_dir, destination):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(os.listdir(out_dir)):
            if not name.startswith('.'):
                zf.write(os.path.join(out_dir, name), name)


def collect(paths):
    """Every skin named by `paths`, which may be packages or directories holding
    them. An unpacked skin is itself a directory, so it is taken as a package if
    it has an info.json and searched for packages otherwise."""
    found = []
    for path in paths:
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.exists(path):
            sys.exit('no such file or directory: %s' % path)
        if os.path.isdir(path) and not os.path.exists(os.path.join(path, 'info.json')):
            inside = sorted(name for name in os.listdir(path)
                            if name.endswith('.deltaskin') and not name.startswith('.'))
            if not inside:
                sys.exit('no .deltaskin packages in %s' % path)
            found.extend(os.path.join(path, name) for name in inside)
        else:
            found.append(path)
    return found


def parse(argv):
    parser = argparse.ArgumentParser(
        prog='animate.py', description=__doc__.split('\n\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Originals are never modified. Run verify.py afterwards to check '
               'the result and to render what a press will look like.')
    parser.add_argument('skins', nargs='+', metavar='SKIN',
                        help='.deltaskin packages, or directories containing them')
    parser.add_argument('-o', '--output', default='animated', metavar='DIR',
                        help='where to write the rebuilt skins (default: ./animated)')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='only report the per-skin totals')
    parser.add_argument('--keep-staging', action='store_true',
                        help='keep the unpacked build directories for inspection')

    glowing = parser.add_argument_group(
        'glow', 'A soft halo around each button while it is held down. The '
                'build is renamed so it installs alongside a plain animated one '
                'instead of replacing it.')
    glowing.add_argument('--glow', action='store_true',
                         help='also add the halo')
    glowing.add_argument('--glow-points', type=float, default=glow.GLOW_POINTS,
                         metavar='PT',
                         help='how far it reaches past the artwork, in points '
                              '(default: %(default)s); a button hemmed in by its '
                              'neighbours gets less')
    glowing.add_argument('--glow-opacity', type=float, default=glow.GLOW_OPACITY,
                         metavar='F',
                         help='how strong it gets at its brightest, 0 to 1 '
                              '(default: %(default)s)')
    glowing.add_argument('--glow-color', '--glow-colour', dest='glow_color',
                         default='auto', metavar='COLOUR',
                         help='what the halo is made of, as a name or #rrggbb '
                              '(default: %(default)s, which is white on any shell '
                              'dark enough to show it and amber on one too pale '
                              'for white to stand out against)')
    glowing.add_argument('--glow-share', type=int, default=glow.GLOW_SHARE,
                         metavar='N',
                         help='how many neighbouring buttons may light together '
                              '(default: %(default)s, a press lighting only its '
                              'own button); raising it lets crowded halos reach '
                              'their full length, at the price of a press '
                              'lighting the whole cluster')
    glowing.add_argument('--glow-inputs', default='play', metavar='LIST',
                         help='which buttons glow: "play" for the controls you '
                              'watch the game through -- the d-pad, face and '
                              'shoulder buttons (default) -- "all" for every '
                              'button including menu and save state, or a '
                              'comma-separated list of Delta input names')
    glowing.add_argument('--no-animate', dest='animate', action='store_false',
                         help='glow only, leaving the buttons themselves still')
    glowing.add_argument('--tag', default=GLOW_TAG, metavar='TEXT',
                         help='what to add to the skin\'s name, and in lower case '
                              'to its identifier (default: %(default)s)')

    options = parser.parse_args(argv)
    if not options.animate and not options.glow:
        parser.error('--no-animate leaves nothing to do; add --glow')
    if not 0 < options.glow_opacity <= 1:
        parser.error('--glow-opacity must be between 0 and 1')
    if options.glow_points < glow.MIN_POINTS:
        parser.error('--glow-points must be at least %g' % glow.MIN_POINTS)
    if options.glow_share < 1:
        parser.error('--glow-share must be at least 1, which is a halo on its own')
    asked = options.glow_inputs.strip()
    options.glow_inputs = (
        None if asked.lower() == 'all' else glow.GLOW_INPUTS
        if asked.lower() == 'play'
        else frozenset(name.strip() for name in asked.split(',') if name.strip()))
    if options.glow_inputs is not None and not options.glow_inputs:
        parser.error('--glow-inputs lists nothing to glow')
    written = options.glow_color.strip().lower().replace(' ', '')
    if written == 'auto':
        options.glow_color = None       # decided per skin; see `glow.suggest_color`
    else:
        try:
            options.glow_color = ImageColor.getrgb(
                GLOW_COLORS.get(written, options.glow_color))[:3]
        except ValueError as problem:
            parser.error('--glow-color: %s' % problem)
    return options


def output_name(name, tag=None):
    """The rebuilt skin's filename, tagged when the build is a variant meant to
    install alongside the original rather than replace it."""
    if not tag:
        return name
    stem, dot, extension = name.rpartition('.')
    return ('%s [%s]%s%s' % (stem, tag, dot, extension) if dot
            else '%s [%s]' % (name, tag))


def main(argv=None):
    options = parse(argv)
    output = os.path.abspath(os.path.expanduser(options.output))
    staging = os.path.join(output, '.staging')
    os.makedirs(output, exist_ok=True)
    tag = options.tag if options.glow else None

    skins = collect(options.skins)
    for path in skins:
        # An overlay cut from an already-animated base would be wrong, and the
        # original would be gone, so check before doing any work.
        if os.path.join(output, output_name(os.path.basename(path), tag)) == path:
            sys.exit('refusing to overwrite the original: %s\n'
                     'choose an --output directory other than the skin\'s own.' % path)

    totals = {'animated': 0, 'glowing': 0, 'companions': 0}
    for path in skins:
        name = os.path.basename(path)
        print(name)
        out_dir = os.path.join(staging, name)
        shutil.rmtree(out_dir, ignore_errors=True)
        os.makedirs(out_dir)
        counts = process(Skin(path), out_dir, verbose=not options.quiet,
                         animating=options.animate, glowing=options.glow,
                         points=options.glow_points, opacity=options.glow_opacity,
                         color=options.glow_color,
                         tag=options.tag, sharing=options.glow_share,
                         inputs=options.glow_inputs)
        destination = os.path.join(output, output_name(name, tag))
        archive(out_dir, destination)
        if not options.keep_staging:
            shutil.rmtree(out_dir, ignore_errors=True)
        for field in totals:
            totals[field] += counts[field]
        print('  %s -> %s\n' % (summary(counts, options), destination))

    if not options.keep_staging:
        shutil.rmtree(staging, ignore_errors=True)
    print('%s across %d skin%s.'
          % (summary(totals, options), len(skins), '' if len(skins) == 1 else 's'))
    if options.glow:
        print('Renamed with [%s], so Delta installs %s alongside the original '
              'rather than over it.' % (options.tag, 'them' if len(skins) > 1 else 'it'))
    return 0


def summary(counts, options):
    parts = []
    if options.animate:
        parts.append('%d animated items' % counts['animated'])
    if options.glow:
        parts.append('%d glowing (%d mask companions)'
                     % (counts['glowing'], counts['companions']))
    return ', '.join(parts)


if __name__ == '__main__':
    sys.exit(main())
