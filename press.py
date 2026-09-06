#!/usr/bin/env python3
"""DeltaCore's press transform, reproduced.

`ControllerView.activateControllerSkinItems` (commit 3e651d9) gives a pressed
item a CATransform3D: buttons scale down so their edge sinks 2 points into the
screen, d-pads tilt so the edge of the pressed side sinks 3 points and then sink
a further point bodily. Core Animation works in row vectors, so its

    transform = scale(...) * rotate(...) * perspective

is, transposed into the column vectors used here, `perspective @ rotate @ scale`:
scale first, then tilt, then the perspective divide.

Knowing exactly where a pressed overlay lands is what lets `animate.py`
size each overlay's band of background to the movement it actually has to cover
(see `band_for`), rather than padding generously and blunting the animation.
"""

import math

PERSPECTIVE_DISTANCE = 500.0    # points; ControllerView's `perspectiveDistance`
BUTTON_DEPTH = 2.0              # points a button's edge sinks
DPAD_EDGE_DEPTH = 3.0           # points the pressed side of a d-pad sinks
DPAD_CENTRE_DEPTH = 1.0         # points the whole d-pad then sinks

# Every state a d-pad can be shown in, as (name, axis) for the tilt. DeltaCore
# prefers the larger angle for diagonals, hence the 'diagonal' spans.
DPAD_STATES = (
    ('centre', None, None),
    ('up', 'vertical', (1, 0, 0)),
    ('down', 'vertical', (-1, 0, 0)),
    ('left', 'horizontal', (0, -1, 0)),
    ('right', 'horizontal', (0, 1, 0)),
    ('up+left', 'diagonal', (0.707, -0.707, 0)),
    ('up+right', 'diagonal', (0.707, 0.707, 0)),
    ('down+left', 'diagonal', (-0.707, -0.707, 0)),
    ('down+right', 'diagonal', (-0.707, 0.707, 0)),
)

DPAD_TILTS = {name: (span, axis) for name, span, axis in DPAD_STATES}


def identity():
    return [[1.0 if row == column else 0.0 for column in range(4)] for row in range(4)]


def multiply(a, b):
    return [[sum(a[row][k] * b[k][column] for k in range(4)) for column in range(4)]
            for row in range(4)]


def scaling(sx, sy):
    matrix = identity()
    matrix[0][0], matrix[1][1] = sx, sy
    return matrix


def perspective():
    """Column-vector form of `transform.m34 = -1/distance`: w = 1 - z/distance."""
    matrix = identity()
    matrix[3][2] = -1.0 / PERSPECTIVE_DISTANCE
    return matrix


def rotation(axis, angle):
    """Rodrigues' formula, in the layer's own coordinate space (y downwards).

    A positive angle about (1, 0, 0) therefore sends the top edge to negative z,
    away from the viewer -- which is what pressing 'up' should look like."""
    length = math.sqrt(sum(component * component for component in axis))
    x, y, z = (component / length for component in axis)
    cos, sin = math.cos(angle), math.sin(angle)
    rest = 1 - cos
    matrix = identity()
    matrix[0][:3] = [cos + x * x * rest, x * y * rest - z * sin, x * z * rest + y * sin]
    matrix[1][:3] = [y * x * rest + z * sin, cos + y * y * rest, y * z * rest - x * sin]
    matrix[2][:3] = [z * x * rest - y * sin, z * y * rest + x * sin, cos + z * z * rest]
    return matrix


def theta(radius, depth=DPAD_EDGE_DEPTH):
    """Tilt that sinks a point `radius` from the centre by `depth` points."""
    ratio = radius / PERSPECTIVE_DISTANCE
    return math.sqrt(ratio ** 2 + 2 * depth / radius) - ratio


def transform(width, height, dpad_direction=None):
    """The matrix DeltaCore applies, for an overlay `width` x `height` points.

    `dpad_direction` is None for a button, or a name from DPAD_STATES."""
    matrix = perspective()
    if dpad_direction is None:
        depth = BUTTON_DEPTH
    else:
        span, axis = DPAD_TILTS[dpad_direction]
        if span is not None:
            horizontal, vertical = theta(width / 2), theta(height / 2)
            angle = {'horizontal': horizontal, 'vertical': vertical,
                     'diagonal': max(horizontal, vertical)}[span]
            matrix = multiply(matrix, rotation(axis, angle))
        depth = DPAD_CENTRE_DEPTH
    return multiply(matrix, scaling(1 - 2 * depth / width, 1 - 2 * depth / height))


def project(matrix, x, y):
    """Where the layer-space point (x, y, 0) lands, after the perspective divide."""
    columns = [matrix[row][0] * x + matrix[row][1] * y + matrix[row][3] for row in range(4)]
    w = columns[3] or 1e-9
    return columns[0] / w, columns[1] / w


def states(is_dpad):
    return [name for name, _, _ in DPAD_STATES] if is_dpad else [None]


def quad(width, height, dpad_direction=None):
    """The overlay's four corners once pressed, in points about its centre.

    Order matches `corners`: top-left, top-right, bottom-right, bottom-left."""
    matrix = transform(width, height, dpad_direction)
    return [project(matrix, x, y) for x, y in corners(width, height)]


def corners(width, height):
    half_w, half_h = width / 2.0, height / 2.0
    return [(-half_w, -half_h), (half_w, -half_h), (half_w, half_h), (-half_w, half_h)]


def solve(matrix, vector):
    """Gauss-Jordan with partial pivoting, for the 8x8 below."""
    size = len(vector)
    rows = [list(row) + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda r: abs(rows[r][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        if abs(divisor) < 1e-12:
            raise ValueError('singular system')
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(size):
            if row != column and rows[row][column]:
                factor = rows[row][column]
                rows[row] = [value - factor * other
                             for value, other in zip(rows[row], rows[column])]
    return [row[size] for row in rows]


def perspective_coefficients(destination, source):
    """The 8 coefficients PIL's Image.PERSPECTIVE wants.

    PIL maps output pixels back to input pixels, so this solves for the inverse
    of `destination <- source`."""
    matrix, vector = [], []
    for (X, Y), (x, y) in zip(destination, source):
        matrix.append([X, Y, 1, 0, 0, 0, -X * x, -Y * x])
        vector.append(x)
        matrix.append([0, 0, 0, X, Y, 1, -X * y, -Y * y])
        vector.append(y)
    return solve(matrix, vector)
