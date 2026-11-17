# SPDX-License-Identifier: GPL-3.0-or-later
"""Curve trimming and corner bevels, independent of Blender's runtime.

Width is distance along each original segment in local curve coordinates.
The original cubic segments are trimmed with de Casteljau subdivision.
"""

from bisect import bisect_left
from math import acos, cos, sqrt, tan

EPS = 1.0e-8


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def mul(a, s):
    return tuple(x * s for x in a)


def length(a):
    return sqrt(sum(x * x for x in a))


def unit(a):
    size = length(a)
    return mul(a, 1.0 / size) if size > EPS else None


def lerp(a, b, t):
    return add(mul(a, 1.0 - t), mul(b, t))


def split(cubic, t):
    a, b, c = (lerp(cubic[i], cubic[i + 1], t) for i in range(3))
    d, e = lerp(a, b, t), lerp(b, c, t)
    p = lerp(d, e, t)
    return (cubic[0], a, d, p), (p, e, c, cubic[3])


def evaluate(cubic, t):
    return split(cubic, t)[0][-1]


def trim(cubic, start, end):
    if start > end:
        return tuple(reversed(trim(cubic, end, start)))
    if start == end:
        return (evaluate(cubic, start),) * 4
    left = split(cubic, end)[0] if end < 1.0 else cubic
    return split(left, start / end)[1] if start > 0.0 else left


def length_table(cubic, samples=128):
    distances = [0.0]
    previous = cubic[0]
    for i in range(1, samples + 1):
        point = evaluate(cubic, i / samples)
        distances.append(distances[-1] + length(sub(point, previous)))
        previous = point
    return distances


def parameter_at_distance(table, distance):
    # Outside the original edge, parameters measure distance along its tangent.
    if distance < 0.0 or distance > table[-1]:
        return distance / table[-1]
    index = min(max(1, bisect_left(table, distance)), len(table) - 1)
    interval = table[index] - table[index - 1]
    fraction = (distance - table[index - 1]) / interval if interval > EPS else 0.0
    return (index - 1 + fraction) / (len(table) - 1)


def direction_at(cubic, t):
    t = max(0.0, min(t, 1.0))
    a, b, c = (sub(cubic[i + 1], cubic[i]) for i in range(3))
    direction = unit(lerp(lerp(a, b, t), lerp(b, c, t), t))
    if direction is not None:
        return direction
    # Zero-length endpoint handles are valid on sharp Bezier corners.
    if t <= EPS:
        return unit(sub(cubic[2], cubic[0])) or unit(sub(cubic[3], cubic[0]))
    if t >= 1.0 - EPS:
        return unit(sub(cubic[3], cubic[1])) or unit(sub(cubic[3], cubic[0]))
    return None


def edge_position(cubic, t, edge_length):
    """Evaluate an edge, extending its endpoint tangents for larger bevels."""
    if t < 0.0:
        return add(cubic[0], mul(direction_at(cubic, 0.0), t * edge_length))
    if t > 1.0:
        return add(cubic[3], mul(direction_at(cubic, 1.0), (t - 1.0) * edge_length))
    return evaluate(cubic, t)


def trim_edge(cubic, start, end, edge_length):
    """Keep exact cubic portions and straight tangent extensions, even reversed."""
    boundaries = [t for t in (0.0, 1.0) if min(start, end) < t < max(start, end)]
    parameters = [start, *sorted(boundaries, reverse=start > end), end]
    pieces = []
    for a, b in zip(parameters, parameters[1:]):
        if 0.0 <= a <= 1.0 and 0.0 <= b <= 1.0:
            piece = trim(cubic, a, b)
        else:
            p = edge_position(cubic, a, edge_length)
            q = edge_position(cubic, b, edge_length)
            piece = (p, lerp(p, q, 1.0 / 3.0), lerp(p, q, 2.0 / 3.0), q)
        pieces.append((piece, b))
    return pieces


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def blend_attributes(a, b, t):
    return {key: a[key] * (1.0 - t) + b[key] * t
            for key in ("radius", "tilt", "weight_softbody")}


def prepare_edges(points, cyclic, bezier):
    """Cache original cubics and arc lengths for interactive previews."""
    edges, tables = [], []
    count = len(points)
    for i in range(count if cyclic else max(0, count - 1)):
        a, b = points[i], points[(i + 1) % count]
        cubic = (a["co"], a["right"], b["left"], b["co"]) if bezier else (
            a["co"], lerp(a["co"], b["co"], 1.0 / 3.0),
            lerp(a["co"], b["co"], 2.0 / 3.0), b["co"])
        edges.append(cubic)
        tables.append(length_table(cubic))
    return edges, tables


def bevel_points(points, cyclic, width, segments=4, rounded=True, bezier=True,
                 amount_type='OFFSET', prepared=None):
    """Return (replacement points, corner count, legacy clamped count of zero).

    Each point is a dict with coordinates, handles and editable attributes.
    Return None for the replacement when the spline has no eligible corners.
    """
    count = len(points)
    if count < 3 or width <= EPS:
        return None, 0, 0
    edge_count = count if cyclic else count - 1
    edges, tables = prepared if prepared is not None else prepare_edges(points, cyclic, bezier)

    corners = {}
    for i, point in enumerate(points):
        if not point["selected"] or point["hide"]:
            continue
        if not cyclic and i in (0, count - 1):
            continue
        before, after = (i - 1) % edge_count, i % edge_count
        incoming, outgoing = direction_at(edges[before], 1.0), direction_at(edges[after], 0.0)
        if incoming is None or outgoing is None:
            continue
        angle_cos = dot(incoming, outgoing)
        # Smooth points need no bevel; a reversing cusp has no well-defined fillet.
        if angle_cos > 1.0 - 1.0e-6 or angle_cos < -1.0 + 1.0e-6:
            continue
        requested = width
        if amount_type == 'RADIUS':
            # For a straight corner, offset = radius * tan(turn / 2).
            requested *= tan(acos(max(-1.0, min(1.0, angle_cos))) / 2.0)
        amount = requested
        if amount <= EPS:
            continue
        end = parameter_at_distance(tables[before], tables[before][-1] - amount)
        start = parameter_at_distance(tables[after], amount)
        a = edge_position(edges[before], end, tables[before][-1])
        b = edge_position(edges[after], start, tables[after][-1])
        incoming = direction_at(edges[before], end)
        outgoing = direction_at(edges[after], start)
        if incoming is None or outgoing is None or length(sub(b, a)) <= EPS:
            continue
        if rounded:
            turn = acos(max(-1.0, min(1.0, dot(incoming, outgoing))))
            handle_length = length(sub(b, a)) / (3.0 * cos(turn / 4.0) ** 2)
            bridge = (a, add(a, mul(incoming, handle_length)),
                      sub(b, mul(outgoing, handle_length)), b)
        else:
            bridge = (a, lerp(a, b, 1.0 / 3.0), lerp(a, b, 2.0 / 3.0), b)
        corners[i] = (end, start, bridge)

    if not corners:
        return None, 0, 0

    trimmed = []
    for i, cubic in enumerate(edges):
        start = corners[i][1] if i in corners else 0.0
        next_index = (i + 1) % count
        end = corners[next_index][0] if next_index in corners else 1.0
        trimmed.append(trim_edge(cubic, start, end, tables[i][-1]))

    result = []
    for i, original in enumerate(points):
        before, after = (i - 1) % edge_count, i % edge_count
        has_before, has_after = cyclic or i > 0, cyclic or i < count - 1
        if i not in corners:
            point = original.copy()
            # Freeze neighboring automatic handles so Blender cannot change a
            # preserved segment after its endpoint has moved.
            if ((has_before and (i - 1) % count in corners)
                    or (has_after and (i + 1) % count in corners)):
                point["left_type"] = point["right_type"] = "FREE"
                if has_before:
                    point["left"] = trimmed[before][-1][0][2]
                if has_after:
                    point["right"] = trimmed[after][0][0][1]
            result.append(point)
        else:
            end, start, bridge = corners[i]
            # Extrapolate geometry, but keep point attributes within their source range.
            attributes_a = blend_attributes(points[(i - 1) % count], original,
                                            max(0.0, min(end, 1.0)))
            attributes_b = blend_attributes(original, points[(i + 1) % count],
                                            max(0.0, min(start, 1.0)))
            pieces = [trim(bridge, j / segments, (j + 1) / segments) for j in range(segments)]
            for j in range(segments + 1):
                point = original.copy()
                point.update(blend_attributes(attributes_a, attributes_b, j / segments))
                point["co"] = pieces[j][0] if j < segments else bridge[3]
                point["left"] = pieces[j - 1][2] if j else trimmed[before][-1][0][2]
                point["right"] = pieces[j][1] if j < segments else trimmed[after][0][0][1]
                point["left_type"] = point["right_type"] = "FREE"
                point["selected"] = True
                point["select_left"] = point["select_right"] = False
                # Non-rational poly curves use homogeneous coordinate 1.
                point["co_weight"] = 1.0
                result.append(point)
        if has_after:
            # Oversized adjacent bevels can traverse an edge backwards and past
            # both endpoints. Keep boundaries so its original cubic stays exact.
            for j, (piece, boundary) in enumerate(trimmed[after][:-1]):
                point = points[i if boundary == 0.0 else (i + 1) % count].copy()
                point["co"] = piece[3]
                point["left"] = piece[2]
                point["right"] = trimmed[after][j + 1][0][1]
                point["left_type"] = point["right_type"] = "FREE"
                point["selected"] = point["select_left"] = point["select_right"] = False
                result.append(point)
    return result, len(corners), 0
