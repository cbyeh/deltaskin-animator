#!/usr/bin/env python3
"""Check the animated skins that animate.py produced.

Three things, in order of how much they matter:

1. Each rebuilt skin still declares the same name and identifier as the original,
   so re-importing it replaces the skin already installed rather than adding a
   second copy. Needs `--original`.
2. At rest every overlay is invisible: compositing them all onto the base image
   has to reproduce that image exactly. This is what makes the skins look
   unchanged until a button is touched, and it catches any error in the crop
   rect, the declared asset size, or the centring maths.
3. Pressed, nothing tears. `press.py` reproduces DeltaCore's transform, so the
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

from PIL import Image, ImageChops

import press
from animate import collect
from skinlib import Skin, kind, label, pixels_per_point, representations

CLOSE_UP_MARGIN = 0.45   # of the item's size, added around a close-up
CLOSE_UP_SCALE = 1.4     # close-ups are rendered a little larger than life


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


def check_metadata(original, rebuilt, name, failures):
    for field in ('name', 'identifier', 'gameTypeIdentifier'):
        if original.info.get(field) != rebuilt.info.get(field):
            failures.append('%s: %s changed from %r to %r'
                            % (name, field, original.info.get(field), rebuilt.info.get(field)))
    for key, rep in representations(rebuilt.info):
        was = dict(representations(original.info))[key]
        if [item['frame'] for item in rep['items']] != [item['frame'] for item in was['items']]:
            failures.append('%s %s: touch targets moved' % (name, '/'.join(key)))
        if rep['assets'] != was['assets']:
            failures.append('%s %s: base artwork changed' % (name, '/'.join(key)))


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
    itself, or a directory to look for it in by name."""
    if path is None:
        return None
    path = os.path.abspath(os.path.expanduser(path))
    if os.path.isdir(path) and not os.path.exists(os.path.join(path, 'info.json')):
        candidate = os.path.join(path, name)
        return candidate if os.path.exists(candidate) else None
    return path


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
    print('Every rest state reproduces its base image exactly%s.'
          % (', and names and identifiers are intact' if options.original else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
