#!/usr/bin/env python3
"""Check the animated skins that animate.py produced.

Four things, in order of how much they matter:

1. Every touch target is untouched, and the skin identifies itself the way it
   should: a plain build keeps the original's name and identifier so re-importing
   it replaces the installed skin, and a `--glow` build carries the tag that lets
   it sit alongside one. Needs `--original`.
2. At rest every overlay is invisible: compositing them all onto the base image
   has to reproduce that image exactly. This is what makes the skins look
   unchanged until a button is touched, and it catches any error in the crop
   rect, the declared asset size, or the centring maths.
3. The glow, where there is one, only ever adds light, appears exactly when its
   button is touched, and doesn't show an edge anywhere -- measured on the
   shipped images, the same way `glow.py` measured it while deciding.
4. Pressed, nothing tears. `press.py` reproduces DeltaCore's transform, so the
   effect can be seen -- and specific buttons inspected close up -- without
   putting the skins on a device.

    python3 verify.py animated/*.deltaskin
    python3 verify.py animated/*.deltaskin --original .
    python3 verify.py animated/"My Skin.deltaskin" --render dpad a b
"""

import argparse
import os
import re
import sys

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFilter

import glow
import press
from animate import MAX_GHOST, collect, find_art, thickness
from skinlib import Skin, kind, label, pixels_per_point, representations

CLOSE_UP_MARGIN = 0.45   # of the item's size, added around a close-up
CLOSE_UP_SCALE = 1.4     # close-ups are rendered a little larger than life
OPAQUE_SLACK = 2         # per channel, how far off the glow colour still counts as it
FRAME_SLACK = 2          # px a button's artwork may reach past its own frame


def base_image(skin, rep):
    return skin.image(list(rep['assets'].values())[0])


def overlay_box(item, rep, size):
    """Where DeltaCore puts the item's overlay, in base-image pixels.

    The overlay is `asset.width` x `asset.height` mapping units, centred on the
    midpoint of the item's frame -- never on the frame itself."""
    frame, asset = item['frame'], item['asset']
    mapping = rep['mappingSize']
    sx, sy = size[0] / mapping['width'], size[1] / mapping['height']
    cx = (frame['x'] + frame['width'] / 2.0) * sx
    cy = (frame['y'] + frame['height'] / 2.0) * sy
    half_w, half_h = asset['width'] * sx / 2.0, asset['height'] * sy / 2.0
    return (round(cx - half_w), round(cy - half_h), round(cx + half_w), round(cy + half_h))


def animated(rep):
    return [item for item in rep['items'] if 'asset' in item]


def is_companion(item):
    """Whether an item is one of the inert mask companions a glow build appends:
    no inputs to fire and no artwork of its own. See `glow.companion`."""
    return item['inputs'] == [] and 'asset' not in item


def real(rep):
    return [item for item in rep['items'] if not is_companion(item)]


def check_rest(skin, name, failures):
    """Overlays at rest must add up to exactly the base image."""
    for key, rep in representations(skin.info):
        base = base_image(skin, rep)
        composite = base.copy()
        items = animated(rep)
        for item in items:
            box = overlay_box(item, rep, base.size)
            overlay = skin.image(item['asset']['name'])
            if overlay.size != (box[2] - box[0], box[3] - box[1]):
                failures.append('%s %s: asset is %dx%d but its box is %dx%d'
                                % (name, item['asset']['name'], overlay.width, overlay.height,
                                   box[2] - box[0], box[3] - box[1]))
                continue
            # Overlays may hang off the edge of the skin, which is legitimate --
            # they are drawn on the view, not into the image -- so clip.
            composite.alpha_composite(overlay, dest=(max(box[0], 0), max(box[1], 0)),
                                      source=(max(-box[0], 0), max(-box[1], 0)))

        difference = ImageChops.difference(base, composite)
        worst = max(channel.getextrema()[1] for channel in difference.split())
        print('    %-30s %2d overlays   rest state differs by %d/255' % ('/'.join(key), len(items), worst))
        if worst > 1:   # 1/255 is alpha-blend rounding; more than that is a real shift
            failures.append('%s %s: rest state differs from the base image by %d/255 at %s'
                            % (name, '/'.join(key), worst, difference.getbbox()))


def retag(original, rebuilt):
    """The tag a glow build appended to the skin's name, or None if it kept it.

    A plain build has to be indistinguishable from the original to Delta so that
    importing it replaces the installed skin; a glow build has to be *distinct*,
    or it would replace the plain one instead of joining it."""
    was, now = original.info.get('name') or '', rebuilt.info.get('name') or ''
    match = re.fullmatch(r'%s \[([^\[\]]+)\]' % re.escape(was), now)
    return match.group(1) if match else None


def check_metadata(original, rebuilt, name, failures):
    tag = retag(original, rebuilt)
    expected = dict(original.info)
    if tag:
        expected['name'] = '%s [%s]' % (original.info.get('name'), tag)
        expected['identifier'] = '%s.%s' % (original.info.get('identifier'), tag.lower())
    for field in ('name', 'identifier', 'gameTypeIdentifier'):
        if expected.get(field) != rebuilt.info.get(field):
            failures.append('%s: %s is %r, expected %r'
                            % (name, field, rebuilt.info.get(field), expected.get(field)))

    for key, rep in representations(rebuilt.info):
        was = dict(representations(original.info))[key]
        # Companions are appended after the originals, so the real items line up.
        # Two keys may have been added to one and nothing else: the `asset`
        # animate.py cuts for it, and the `mask` a glow build can set to shrink the
        # region a press uncovers to the disc inside the frame. Neither moves a touch
        # target -- DeltaCore hit-tests `frame` and `extendedEdges`, and reads `mask`
        # only in `ButtonsInputView.updateInputs` -- so `mask` is checked on its own
        # below rather than counted as the item having changed.
        kept = [{field: value for field, value in item.items()
                 if field not in ('asset', 'mask')} for item in real(rep)]
        plain = [{field: value for field, value in item.items() if field != 'mask'}
                 for item in was['items']]
        for index, (now, before) in enumerate(zip(real(rep), was['items'])):
            allowed = (before.get('mask'), glow.ROUND)
            if now.get('mask', before.get('mask')) not in allowed:
                failures.append('%s %s: item %d asks for mask %r, not %s'
                                % (name, '/'.join(key), index, now.get('mask'),
                                   ' or '.join(repr(value) for value in allowed)))
        if kept != plain:
            differing = [index for index, (now, before)
                         in enumerate(zip(kept, plain)) if now != before]
            failures.append('%s %s: %s'
                            % (name, '/'.join(key),
                               'item count changed from %d to %d'
                               % (len(plain), len(kept))
                               if len(kept) != len(plain)
                               else 'items %s were modified' % differing))
        if rep['assets'] != was['assets']:
            failures.append('%s %s: base artwork changed' % (name, '/'.join(key)))


def check_glow(skin, name, failures):
    """The `_pressed` images, if there are any, and the companions that show them."""
    available = set(skin.names())
    for key, rep in representations(skin.info):
        extra = [item for item in rep['items'] if is_companion(item)]
        assets = list(dict.fromkeys(rep['assets'].values()))
        missing = [asset for asset in assets
                   if glow.pressed_name(asset) not in available]
        if not extra and len(missing) == len(assets):
            continue                            # not a glow build
        if missing:
            failures.append('%s %s: no %s, so those asset sizes glow not at all'
                            % (name, '/'.join(key), ', '.join(missing)))

        # A companion must light exactly with its partner, which is what an
        # identical extendedFrame buys -- see glow.py. Anything else would make
        # the glow appear under a finger that isn't on the button. A d-pad's
        # companions are pinned to one of its directional zones instead, so they
        # light one arm at a time.
        targets = {glow.extended_box(item, rep) for item in real(rep)}
        targets |= {zone for item in real(rep) if glow.directional(item)
                    for zone in glow.zones(item, rep).values()}
        for item in extra:
            if glow.extended_box(item, rep) not in targets:
                failures.append('%s %s: a mask companion at %r lights on its own, '
                                'not with any item' % (name, '/'.join(key), item['frame']))

        base = base_image(skin, rep)
        pressed = skin.image(glow.pressed_name(assets[0]))
        if pressed.size != base.size:
            failures.append('%s %s: the pressed image is %dx%d, not %dx%d'
                            % (name, '/'.join(key), pressed.width, pressed.height,
                               base.width, base.height))
            continue
        # The glow is one colour laid over the base at varying strength, so every
        # channel of every pixel has to come out somewhere between the two. White
        # can only lighten; amber over a blue button darkens its blue channel, and
        # still must not take it past amber's own.
        was, now = visible(base), visible(pressed)
        stray = wandered(was, now, glow_color(skin.info))
        if stray:
            failures.append('%s %s: the pressed image is %d/255 past the glow '
                            'colour somewhere -- it should only blend towards it'
                            % (name, '/'.join(key), stray))

        difference = ImageChops.difference(was, now)
        worst, culprit = edge_steps(rep, difference)
        print('    %-30s %2d companions  worst mask edge %d/255'
              % ('/'.join(key), len(extra), worst))
        if worst > glow.EDGE_TOLERANCE:
            failures.append('%s %s: %s cuts the glow at %d/255 -- a visible edge'
                            % (name, '/'.join(key), culprit, worst))
        for found, pressing, peer in strays(rep, difference):
            failures.append('%s %s: pressing %s lights %s at %d/255 -- a halo that '
                            'is not under the finger'
                            % (name, '/'.join(key), pressing, peer, found))


def check_ghosts(skin, name, failures):
    """Pressed, no overlay uncovers the button it left behind.

    An overlay is drawn over the base image, and the base image still has the
    button painted where it was, so a shrinking overlay uncovers that edge unless
    something covers it. Two things can: a band of surrounding background carried
    along by the overlay, or -- on a glowing button, whose overlay carries no band
    at all so that nothing of it lands on the halo -- the halo itself, at full
    strength, in the ring the press vacates.

    Both come to the same picture on screen, so both are measured here rather than
    in the build: for every press state, whatever the moved overlay no longer covers
    has to be covered by opaque glow instead. The build's own measurement was of the
    overlay alone, which is exactly the blind spot that let a band of background sit
    on top of a halo through several releases.

    Only what the press uncovers *of the button itself* counts: a band is background,
    so its own rim sliding inward uncovers background that looks the same either way.
    So the artwork is located again, by the same detection the build ran over the same
    base image, and the gap is measured inside that."""
    for key, rep in representations(skin.info):
        base = base_image(skin, rep)
        ppp = pixels_per_point(key, base)
        scale = (base.width / float(rep['mappingSize']['width']),
                 base.height / float(rep['mappingSize']['height']))
        assets = list(dict.fromkeys(rep['assets'].values()))
        name_pressed = glow.pressed_name(assets[0])
        lit = None
        if name_pressed in set(skin.names()):
            lit = opaque(base, skin.image(name_pressed), glow_color(skin.info))
        worst = (0, None)
        for item in animated(rep):
            overlay = skin.image(item['asset']['name'])
            box = overlay_box(item, rep, base.size)
            if overlay.size != (box[2] - box[0], box[3] - box[1]):
                continue                        # check_rest reports that already
            rest = ImageChops.multiply(
                overlay.split()[3].point(lambda v: 255 if v >= 200 else 0),
                artwork(base, item, ppp, box, overlay.size, scale))
            covered = None
            for direction in press.states(kind(item) == 'dPad'):
                moved, shift = pressed(overlay, ppp, direction)
                state = Image.new('L', overlay.size)
                state.paste(moved.split()[3], (shift[0], shift[1]))
                state = state.filter(ImageFilter.MaxFilter(3)).point(
                    lambda v: 255 if v >= 200 else 0)
                covered = state if covered is None else ImageChops.darker(covered, state)
            gap = ImageChops.subtract(rest, covered)
            if lit is not None:
                patch = Image.new('L', overlay.size)
                inner = intersect(box, (0, 0, base.width, base.height))
                if inner is not None:
                    patch.paste(lit.crop(inner), (inner[0] - box[0], inner[1] - box[1]))
                gap = ImageChops.subtract(gap, patch)
            found = thickness(gap)
            if found > worst[0]:
                worst = (found, label(item))
        print('    %-30s worst uncovered edge %dpx' % ('/'.join(key), 2 * worst[0] + 1))
        if worst[0] > MAX_GHOST:
            failures.append('%s %s: pressing %s uncovers %dpx of the button drawn '
                            'in the base image -- a ghosted edge'
                            % (name, '/'.join(key), worst[1], 2 * worst[0] + 1))


def artwork(base, item, ppp, box, size, scale):
    """Where the button itself is painted, in the overlay's own coordinates.

    Located the way the build located it, off the same base image -- check_metadata
    holds that image unchanged, so the answer is the one the band was measured
    against. If detection comes up empty, the item's frame stands in, grown a little
    for artwork that reaches past it."""
    stencil = Image.new('L', size, 0)
    entry = find_art(base, item, ppp)
    if entry is not None:
        art, at = entry['interior'], entry['view']['box']
        stencil.paste(art.point(lambda v: 255 if v else 0),
                      (at[0] - box[0], at[1] - box[1]))
        return stencil
    frame = glow.scaled(glow.frame_box(item), scale)
    ImageDraw.Draw(stencil).rectangle(
        (frame[0] - box[0] - FRAME_SLACK, frame[1] - box[1] - FRAME_SLACK,
         frame[2] - box[0] + FRAME_SLACK - 1, frame[3] - box[1] + FRAME_SLACK - 1),
        fill=255)
    return stencil


def opaque(base, pressed, color):
    """Where the pressed image has replaced the base outright with the glow colour.

    A halo at full strength is the colour and nothing of what it lies over, which is
    what lets it stand in for a band: whatever was painted underneath -- the button's
    own edge included -- is gone. Anything short of full strength still shows some of
    it, so nothing short of full strength counts here."""
    stencil = None
    for channel in range(3):
        band = ImageChops.difference(
            pressed.convert('RGB').split()[channel],
            Image.new('L', pressed.size, color[channel])).point(
                lambda v: 255 if v <= OPAQUE_SLACK else 0)
        stencil = band if stencil is None else ImageChops.multiply(stencil, band)
    return ImageChops.multiply(stencil, ImageChops.difference(
        base.convert('RGB'), pressed.convert('RGB')).convert('L').point(
            lambda v: 255 if v > 1 else 0))


def intersect(a, b):
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[2] > box[0] and box[3] > box[1] else None


def visible(image):
    """The light an image actually puts on the display: its colour weighted by its
    own alpha.

    Comparing raw channels is misleading wherever the skin is transparent -- over
    a cut-out screen area the base reads as black and the faintest white laid on
    top of it reads as pure white, a difference of 255 for a pixel the device
    draws at 1/255."""
    alpha = image.getchannel('A')
    return Image.merge('RGB', [ImageChops.multiply(channel, alpha)
                               for channel in image.split()[:3]])


def glow_color(info):
    """The colour the glow was built from, which `animate.py` records in the skin.
    An older build, or one from another tool, is taken to be white."""
    written = (info.get('glow') or {}).get('color') or '#ffffff'
    return ImageColor.getrgb(written)[:3]


def wandered(was, now, color):
    """How far outside the range from `was` to `color` the pressed image strays,
    per channel and at worst.

    Compositing one colour over another lands between the two, whatever the
    alpha, so anything outside that range came from somewhere else -- a misplaced
    crop, or a glow that isn't the colour it says it is."""
    worst = 0
    for before, after, level in zip(was.split(), now.split(), color):
        flat = Image.new('L', before.size, level)
        past = ImageChops.subtract(after, ImageChops.lighter(before, flat))
        short = ImageChops.subtract(ImageChops.darker(before, flat), after)
        worst = max(worst, past.getextrema()[1], short.getextrema()[1])
    return worst


def edge_steps(rep, difference):
    """The brightest the glow gets along the outside of any item's mask.

    DeltaCore draws the pressed image inside the frames of the items a touch is
    on and the base image outside them, so whatever the two differ by along that
    dividing line is a hard edge on screen. An item that asked for `mask: circle`
    contributes the disc inside its frame rather than the frame, and the rim of that
    disc is the line to measure. Measured here on the shipped images rather than on
    what `glow.py` thought it was making."""
    field = difference.convert('L')
    mapping = rep['mappingSize']
    scale = (field.width / mapping['width'], field.height / mapping['height'])
    boxes = [glow.scaled(glow.mask_box(item), scale) for item in rep['items']]
    lit = {index: glow.extended_box(item, rep)
           for index, item in enumerate(rep['items']) if is_companion(item)}

    worst, culprit = 0, None
    for index, item in enumerate(rep['items']):
        if is_companion(item):
            continue
        # Everything a touch on this item can put into the mask: its own frame,
        # the companions pinned to it, and -- for a d-pad -- those pinned to its
        # directional zones, whose union is the same region a single companion
        # covered before they were split up. See `glow.bands`.
        wearing = {glow.extended_box(item, rep)}
        if glow.directional(item):
            wearing |= set(glow.zones(item, rep).values())
        regions = [boxes[index]] + [boxes[other] for other, where in lit.items()
                                    if where in wearing]
        for which, found in glow.steps({'field': {'box': (0, 0) + field.size,
                                                  'alpha': field,
                                                  'offset': (0, 0)}}, regions):
            if found > worst:
                worst, culprit = found, ('%s\'s own frame' % label(item) if which == 0
                                         else 'a mask companion of %s' % label(item))
    return worst, culprit


CORE = 0.35             # how much of a button's width counts as its middle


def strays(rep, difference):
    """Every press that lights a button other than the one under the thumb.

    The pressed image holds every halo at once and the mask uncovers the part
    under the finger, so a mask reaching as far as a neighbour's glow would light
    that neighbour too. `edge_steps` cannot see this -- a halo sitting wholly
    inside somebody else's region has no edge running through it at all -- so this
    looks at the middle of every other glowing button, where nothing but that
    button's own bloom has any business being. Two items wired to the same input
    are the exception: DeltaCore fires both, so both are meant to light.

    One touch per item stands for all of them: its centre, or the middle of its
    `up` zone for a d-pad, which is the press each halo was built around."""
    field = difference.convert('L')
    mapping = rep['mappingSize']
    scale = (field.width / mapping['width'], field.height / mapping['height'])
    glowing = [item for item in rep['items'] if item.get('asset')]

    found = []
    for item in glowing:
        ext = glow.extended_box(item, rep)
        high = 0.1 if glow.directional(item) else 0.5
        probe = ((ext[0] + ext[2]) / 2.0, ext[1] + (ext[3] - ext[1]) * high)
        mask = Image.new('L', field.size, 0)
        draw = ImageDraw.Draw(mask)
        for other in rep['items']:
            box = glow.extended_box(other, rep)
            if box[0] <= probe[0] < box[2] and box[1] <= probe[1] < box[3]:
                region = glow.scaled(glow.mask_box(other), scale)
                shape = (region[0], region[1], region[2] - 1, region[3] - 1)
                (draw.ellipse if glow.is_round(region) else draw.rectangle)(
                    shape, fill=255)
        seen = ImageChops.darker(field, mask)
        for peer in glowing:
            if peer is item or glow.input_names(peer) & glow.input_names(item):
                continue
            box = glow.scaled(glow.frame_box(peer), scale)
            edge = ((box[2] - box[0]) * (1 - CORE) / 2.0,
                    (box[3] - box[1]) * (1 - CORE) / 2.0)
            core = (box[0] + edge[0], box[1] + edge[1],
                    box[2] - edge[0], box[3] - edge[1])
            worst = seen.crop([int(round(value)) for value in core]).getextrema()[1]
            if worst > glow.EDGE_TOLERANCE:
                found.append((worst, label(item), label(peer)))
    return sorted(found, reverse=True)


def pressed(overlay, ppp, direction):
    """`overlay` as DeltaCore draws it when pressed, on a canvas with room for a
    d-pad's tilt to lean out of. Returns the image and where its top-left corner
    sits relative to the overlay's."""
    pad = max(8, round(0.1 * max(overlay.size)))
    canvas = (overlay.width + 2 * pad, overlay.height + 2 * pad)
    rest = Image.new('RGBA', canvas)
    rest.paste(overlay, (pad, pad))

    source = [(pad, pad), (pad + overlay.width, pad),
              (pad + overlay.width, pad + overlay.height), (pad, pad + overlay.height)]
    centre = (canvas[0] / 2.0, canvas[1] / 2.0)
    quad = press.quad(overlay.width / ppp, overlay.height / ppp, direction)
    destination = [(centre[0] + x * ppp, centre[1] + y * ppp) for x, y in quad]
    coefficients = press.perspective_coefficients(destination, source)
    return rest.transform(canvas, Image.PERSPECTIVE, coefficients, Image.BICUBIC), (-pad, -pad)


def render(skin, rep, ppp, only=None, direction='up'):
    """The representation with every animated item (or just `only`) held down."""
    base = base_image(skin, rep)
    composite = base.copy()
    touched = []
    for item in animated(rep):
        if only and label(item) not in only:
            continue
        box = overlay_box(item, rep, base.size)
        moved, shift = pressed(skin.image(item['asset']['name']), ppp,
                               direction if kind(item) == 'dPad' else None)
        composite.alpha_composite(moved, dest=(max(box[0] + shift[0], 0), max(box[1] + shift[1], 0)),
                                  source=(max(-(box[0] + shift[0]), 0), max(-(box[1] + shift[1]), 0)))
        touched.append((item, box))
    return composite, touched


def close_up(before, after, box):
    """The same region before and after, side by side, for eyeballing."""
    width, height = box[2] - box[0], box[3] - box[1]
    pad = (round(CLOSE_UP_MARGIN * width), round(CLOSE_UP_MARGIN * height))
    region = (max(box[0] - pad[0], 0), max(box[1] - pad[1], 0),
              min(box[2] + pad[0], before.width), min(box[3] + pad[1], before.height))
    panels = [image.crop(region).convert('RGB') for image in (before, after)]
    strip = Image.new('RGB', (panels[0].width * 2 + 8, panels[0].height), (255, 0, 255))
    strip.paste(panels[0], (0, 0))
    strip.paste(panels[1], (panels[0].width + 8, 0))
    if CLOSE_UP_SCALE != 1.0:
        strip = strip.resize((round(strip.width * CLOSE_UP_SCALE),
                             round(strip.height * CLOSE_UP_SCALE)), Image.LANCZOS)
    return strip


def stem(name):
    return re.sub(r'[^A-Za-z0-9]+', '-', name.replace('.deltaskin', '')).strip('-')


def find_original(path, name):
    """The original matching a rebuilt skin, given `--original`: either the skin
    itself, or a directory to look for it in by name.

    A glow build's filename carries the same tag as its name, so the untagged
    filename is tried as well."""
    if path is None:
        return None
    path = os.path.abspath(os.path.expanduser(path))
    if not (os.path.isdir(path) and not os.path.exists(os.path.join(path, 'info.json'))):
        return path
    untagged = re.sub(r' \[[^\[\]]+\]\.deltaskin$', '.deltaskin', name)
    for candidate in (name, untagged):
        if os.path.exists(os.path.join(path, candidate)):
            return os.path.join(path, candidate)
    return None


def parse(argv):
    parser = argparse.ArgumentParser(
        prog='verify.py', description=__doc__.split('\n\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('skins', nargs='+', metavar='SKIN',
                        help='rebuilt .deltaskin packages, or a directory of them')
    parser.add_argument('--original', metavar='PATH',
                        help='the matching original skin, or a directory of originals, '
                             'to compare names and touch targets against')
    parser.add_argument('--render', nargs='*', metavar='ITEM',
                        help='write before/after close-ups; name items (dpad, a, start) '
                             'to limit it to those')
    parser.add_argument('--overview', action='store_true',
                        help='write a whole-view render of each representation')
    parser.add_argument('--renders', default='renders', metavar='DIR',
                        help='where to write images (default: ./renders)')
    return parser.parse_args(argv)


def main(argv=None):
    options = parse(argv)
    only = set(options.render) if options.render else None
    drawing = options.render is not None or options.overview
    renders = os.path.abspath(os.path.expanduser(options.renders))
    if drawing:
        os.makedirs(renders, exist_ok=True)

    paths = collect(options.skins)   # accepts directories, as animate.py does

    failures = []
    for path in paths:
        name = os.path.basename(path)
        print(name)
        rebuilt = Skin(path)

        original = find_original(options.original, name)
        if original:
            check_metadata(Skin(original), rebuilt, name, failures)
        elif options.original:
            failures.append('%s: no matching original in %s' % (name, options.original))
        check_rest(rebuilt, name, failures)
        check_glow(rebuilt, name, failures)
        check_ghosts(rebuilt, name, failures)

        for key, rep in representations(rebuilt.info):
            base = base_image(rebuilt, rep)
            ppp = pixels_per_point(key, base)
            if options.overview:
                composite, _ = render(rebuilt, rep, ppp)
                whole = composite.resize((composite.width // 3, composite.height // 3),
                                         Image.LANCZOS)
                out = '%s_%s.png' % (stem(name), key[2])
                whole.save(os.path.join(renders, out))
                print('    %s' % out)
            if options.render is None:
                continue
            # Both an axis-aligned and a diagonal press: a d-pad's corners travel
            # furthest diagonally, which is where a band comes up short first.
            for direction in ('up', 'down+right'):
                composite, touched = render(rebuilt, rep, ppp, only, direction)
                for item, box in touched:
                    out = '%s_%s_%s_%s.png' % (stem(name), key[2], label(item), direction)
                    close_up(base, composite, box).save(os.path.join(renders, out))
                    print('    %s' % out)
        print()

    if failures:
        print('FAILURES:')
        for failure in failures:
            print('  ' + failure)
        return 1
    print('Every rest state reproduces its base image exactly, no glow shows an '
          'edge, no press leaves the button it moved off behind, a press lights '
          'nothing but the button under it%s.'
          % (', and every touch target is where it was'
             if options.original else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
