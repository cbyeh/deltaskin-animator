#!/usr/bin/env python3
"""Shared plumbing for reading .deltaskin packages and finding button artwork.

A .deltaskin is a zip archive, though Delta will also happily read an unpacked
directory, and both forms turn up in practice, so `Skin` handles either.

The interesting part is the artwork search: Delta's animated skins (commit
3e651d9) expect a separate image per button, which Riley cut from the layered
source art before flattening the skin. We only have the flattened PNG, so the
artwork has to be found in it -- see `detect_interior` for how, `band_alpha` for
what gets carried along with it, and `animate.py` for why.
"""

import io
import json
import os
import zipfile

from PIL import Image, ImageChops, ImageDraw, ImageFilter

# Tuning constants are in points; callers pass `ppp` (pixels per point) worked
# out from the representation, since a skin's mapping units are its own.

RIM_POINTS = 4.0        # how far past the flat interior a button's rim/shadow reaches
RIM_FRACTION = 0.35     # but never more than this much of the interior's short side

SEED_GRID = 5           # seeds per axis, spread over the item's frame
SEED_INSET = 0.16       # fraction of the frame skipped at each side when seeding
MAX_REGION = 2.5        # a smooth region larger than this * frame area is background

# High-pass response counting as an edge, tried in order. A rim drawn in low
# contrast (the N64's dark menu keys on a dark bezel) needs a lower bar before it
# fences its button in, but a low bar also turns background texture (carbon
# weave, camo) into fencing, so start strict and only relax if nothing is found.
EDGE_THRESHOLDS = (8, 5, 3)

# Screen width in points, per device and orientation. Used only to turn the
# point-based tuning constants above into pixels, so rough values are fine --
# a skin's own mapping units are arbitrary and tell us nothing about scale.
VIEW_POINTS = {
    ('iphone', 'portrait'): 430.0, ('iphone', 'landscape'): 932.0,
    ('ipad', 'portrait'): 834.0, ('ipad', 'landscape'): 1194.0,
}


def pixels_per_point(key, base):
    """Image pixels per point, for the representation `key` and its base image."""
    return base.width / VIEW_POINTS.get((key[0], key[2]), 430.0)


class Skin:
    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path) if os.path.isfile(path) else None
        self.info = json.loads(self.read('info.json'))

    def names(self):
        if self.zip:
            return [n for n in self.zip.namelist()
                    if not n.startswith('__MACOSX/') and not n.endswith('/')]
        return [n for n in sorted(os.listdir(self.path)) if not n.startswith('.')]

    def read(self, name):
        if self.zip:
            return self.zip.read(name)
        with open(os.path.join(self.path, name), 'rb') as file:
            return file.read()

    def image(self, name):
        return Image.open(io.BytesIO(self.read(name))).convert('RGBA')


def representations(info):
    for device, by_display in info['representations'].items():
        for display, by_orientation in by_display.items():
            for orientation, rep in by_orientation.items():
                yield (device, display, orientation), rep


def label(item):
    inputs = item['inputs']
    if isinstance(inputs, list):
        return '+'.join(inputs)
    return {'up': 'dpad', 'cUp': 'cpad', 'analogStickUp': 'thumbstick'}.get(
        inputs.get('up', ''), 'touchscreen' if 'x' in inputs else 'directional')


def kind(item):
    inputs = item['inputs']
    if isinstance(inputs, list):
        return 'button'
    if 'x' in inputs or 'y' in inputs:
        return 'touchScreen'
    return 'thumbstick' if 'thumbstick' in item else 'dPad'


# --- masks as flat bytearrays ----------------------------------------------
# Pillow has no connected-component labelling and its floodfill is per-pixel
# Python, so the region growing below runs on bytearrays with a scanline fill.

def to_bytes(mask):
    return bytearray(mask.tobytes())


def to_image(data, size):
    return Image.frombytes('L', size, bytes(data))


def flood(data, size, seed, mark):
    """Scanline flood fill of the 255-valued region at `seed`. Returns (area, bbox)."""
    width, height = size
    x0, y0 = seed
    if data[y0 * width + x0] != 255:
        return 0, None

    area = 0
    left = right = x0
    top = bottom = y0
    stack = [(x0, x0, y0)]
    while stack:
        sx1, sx2, y = stack.pop()
        row = y * width
        x = sx1
        while x <= sx2:
            if data[row + x] != 255:
                x += 1
                continue
            start = x
            while start > 0 and data[row + start - 1] == 255:
                start -= 1
            end = x
            while end + 1 < width and data[row + end + 1] == 255:
                end += 1
            for i in range(row + start, row + end + 1):
                data[i] = mark
            area += end - start + 1
            left, right = min(left, start), max(right, end)
            top, bottom = min(top, y), max(bottom, y)
            if y > 0:
                stack.append((start, end, y - 1))
            if y + 1 < height:
                stack.append((start, end, y + 1))
            x = end + 1
    return area, (left, top, right + 1, bottom + 1)


def fill_holes(data, size):
    """Add to `data` (255/0) any 0-region not connected to the border."""
    width, height = size
    outside = bytearray(255 if value == 0 else 0 for value in data)
    for x in range(width):
        flood(outside, size, (x, 0), 1)
        flood(outside, size, (x, height - 1), 1)
    for y in range(height):
        flood(outside, size, (0, y), 1)
        flood(outside, size, (width - 1, y), 1)
    for i, value in enumerate(outside):
        if value == 255:          # enclosed background: part of the button
            data[i] = 255


def dilate(mask, radius):
    """Chebyshev dilation, in steps Pillow can do in C."""
    while radius > 0:
        step = min(radius, 2)
        mask = mask.filter(ImageFilter.MaxFilter(2 * step + 1))
        radius -= step
    return mask


def dilate_within(mask, allowed, radius):
    """Grow `mask` outwards but never into a 0 pixel of `allowed`."""
    for _ in range(radius):
        mask = ImageChops.multiply(mask.filter(ImageFilter.MaxFilter(3)), allowed)
    return mask


# --- artwork detection ------------------------------------------------------

def wall_map(crop, threshold, outside=None):
    """Where the artwork has edges: a high-pass of the image, thresholded.

    Buttons are drawn as flat or softly shaded shapes fenced in by their own rim,
    so these walls enclose each one and separate it from its background."""
    gray = crop.convert('L')
    edges = ImageChops.difference(gray, gray.filter(ImageFilter.GaussianBlur(1.5)))
    walls = edges.point(lambda v: 255 if v >= threshold else 0)
    walls = walls.filter(ImageFilter.MaxFilter(3))      # close 1px gaps in a rim
    if outside is not None:
        walls = ImageChops.lighter(walls, outside)      # the skin's own edge is a wall
    return walls


def detect_interior(walls, frame_box, open_sides=(), report=None):
    """The artwork's flat interior: every smooth region overlapping `frame_box`.

    Flooding from a grid of seeds picks up each such region (four separate C
    buttons as readily as one d-pad cross) and discards any that spills out into
    the background, which is what happens when a button's rim is too faint or too
    broken -- a dashed outline, say -- to fence it in."""
    size = walls.size
    width, height = size
    smooth = to_bytes(ImageChops.invert(walls))
    frame_area = max(1, (frame_box[2] - frame_box[0]) * (frame_box[3] - frame_box[1]))
    art = bytearray(width * height)
    kept = 0

    for row in range(SEED_GRID):
        for column in range(SEED_GRID):
            fx = SEED_INSET + (1 - 2 * SEED_INSET) * (column / (SEED_GRID - 1))
            fy = SEED_INSET + (1 - 2 * SEED_INSET) * (row / (SEED_GRID - 1))
            x = int(frame_box[0] + fx * (frame_box[2] - frame_box[0]))
            y = int(frame_box[1] + fy * (frame_box[3] - frame_box[1]))
            if not (0 <= x < width and 0 <= y < height):
                continue
            if smooth[y * width + x] != 255:
                continue                                # on a wall, or already taken

            region = bytearray(smooth)
            area, box = flood(region, size, (x, y), 1)
            if not box:
                continue

            escaped = ((box[0] == 0 and 'left' not in open_sides)
                       or (box[1] == 0 and 'top' not in open_sides)
                       or (box[2] == width and 'right' not in open_sides)
                       or (box[3] == height and 'bottom' not in open_sides))
            if escaped or area > MAX_REGION * frame_area:
                for i, value in enumerate(region):
                    if value == 1:
                        smooth[i] = 0                   # don't seed into it again
                if report is not None:
                    report.append('dropped region at (%d,%d) area=%d %s'
                                  % (x, y, area, 'escaped' if escaped else 'too large'))
                continue

            for i, value in enumerate(region):
                if value == 1:
                    art[i] = 255
                    smooth[i] = 0
            kept += 1

    if not kept:
        return None, 0
    fill_holes(art, size)
    return to_image(art, size), sum(1 for value in art if value)


def shape_interior(size, frame_box):
    """Fallback interior: the item's frame as a rounded shape (a circle when the
    frame is square, a capsule when it is long). Used where the artwork can't be
    made out; every button still animates, it just moves a shape we assumed
    rather than one we measured."""
    mask = Image.new('L', size, 0)
    box = (frame_box[0], frame_box[1], frame_box[2] - 1, frame_box[3] - 1)
    radius = min(box[2] - box[0], box[3] - box[1]) / 2.0
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    return mask


def rim_radius(interior, ppp):
    """How far to reach past the flat interior for the rim and drop shadow.

    A fraction of the interior's short side, so a small button isn't doubled in
    size by a rim allowance meant for a large one."""
    box = interior.getbbox()
    short = min(box[2] - box[0], box[3] - box[1]) if box else 0
    return max(1, min(round(RIM_POINTS * ppp), round(RIM_FRACTION * short)))


def band_alpha(crop, interior, walls, ppp, band, feather):
    """The overlay's alpha, and the artwork inside it that a press must not expose.

    The detected interior stops short of the rim, so it is first grown by
    `rim_radius` through anything, picking the rim and drop shadow back up. That
    whole shape is the artwork: when the overlay moves, every pixel of it has to
    end up covered again, or its old edge shows through as a ghost.

    Covering it is what the band is for. It grows `band` pixels further, through
    smooth background only, stopping dead at any edge that isn't the button's own
    -- which is what keeps a neighbouring plate, screen or bezel from being
    dragged along. The outer `feather` pixels fade out so the band's own edge
    can't tear a seam. `animate.py` picks the narrowest band that actually
    covers, since every pixel of band makes the overlay bigger and the animation
    correspondingly smaller."""
    rim = rim_radius(interior, ppp)
    # Anything further from the interior than the rim belongs to something else.
    foreign = ImageChops.subtract(walls, dilate(interior, rim + 1))
    allowed = ImageChops.invert(foreign)
    # Reaching for the rim has to stop at those edges as well, or the artwork is
    # recorded as extending past whatever the button sits on -- the N64's A button
    # is tangent to the edge of its plate, and a rim allowance that steps over it
    # would claim the black beyond as part of the button and demand it be covered.
    art = dilate_within(interior, allowed, rim)
    banded = dilate_within(art, allowed, band)

    sigma = max(1.0, feather / 2.0)
    faded = banded.filter(ImageFilter.GaussianBlur(sigma)).point(lambda v: min(255, v * 2))
    # Keep the fade itself from painting over foreign edges either.
    gate = allowed.filter(ImageFilter.GaussianBlur(sigma / 2)).point(lambda v: min(255, v * 2))
    alpha = ImageChops.multiply(faded, ImageChops.lighter(gate, banded))

    # Duplicating a translucent pixel would render it twice, so only fully
    # opaque artwork is carried -- and what isn't carried can't be exposed.
    opaque = crop.getchannel('A').point(lambda v: 255 if v == 255 else 0)
    return ImageChops.multiply(alpha, opaque), ImageChops.multiply(art, opaque)
