# SPDX-License-Identifier: GPL-3.0-or-later
"""Curve point movement and sliding along the original neighboring segments."""

from .geometry import EPS, add, sub, edge_position, parameter_at_distance, prepare_edges


def prepare_slide(points, cyclic, bezier):
    paths = {}
    if len(points) < 2:
        return paths
    edges, tables = prepare_edges(points, cyclic, bezier)
    for i, point in enumerate(points):
        if not point['selected'] or point['hide']:
            continue
        before = after = None
        if (cyclic or i > 0) and not points[(i - 1) % len(points)]['hide']:
            j = (i - 1) % len(edges)
            if tables[j][-1] > EPS:
                before = (edges[j], tables[j])
        if (cyclic or i < len(points) - 1) and not points[(i + 1) % len(points)]['hide']:
            j = i % len(edges)
            if tables[j][-1] > EPS:
                after = (edges[j], tables[j])
        if before or after:
            paths[i] = (before, after)
    return paths


def position_on_path(point, paths, factor, clamp=True):
    """Signed arc-length fraction: negative towards previous, positive towards next."""
    if clamp:
        factor = max(-1.0, min(factor, 1.0))
    before, after = paths
    if factor >= 0 and after:
        cubic, table = after
        distance = factor * table[-1]
    elif factor < 0 and before:
        cubic, table = before
        distance = (1.0 + factor) * table[-1]
    elif not clamp and before:
        cubic, table = before
        distance = (1.0 + factor) * table[-1]
    elif not clamp and after:
        cubic, table = after
        distance = factor * table[-1]
    else:
        return point['co']
    return edge_position(cubic, parameter_at_distance(table, distance), table[-1])


def slide_points(points, paths, factor, clamp=True):
    result = [point.copy() for point in points]
    for index, neighbors in paths.items():
        original, point = points[index], result[index]
        point['co'] = position_on_path(original, neighbors, factor, clamp)
        delta = sub(point['co'], original['co'])
        point['left'] = add(original['left'], delta)
        point['right'] = add(original['right'], delta)
    return result


def move_points(points, delta):
    result = [point.copy() for point in points]
    for original, point in zip(points, result):
        if original['hide']:
            continue
        if original['selected']:
            for name in ('co', 'left', 'right'):
                point[name] = add(original[name], delta)
        else:
            if original['select_left']:
                point['left'] = add(original['left'], delta)
            if original['select_right']:
                point['right'] = add(original['right'], delta)
    return result


def nearest_factor(projected_paths, target, clamp=True):
    """Closest point on projected arc samples; tangent extension remains unbounded."""
    best = None
    for path in projected_paths:
        for i, ((a_factor, a), (b_factor, b)) in enumerate(zip(path, path[1:])):
            delta = (b[0] - a[0], b[1] - a[1])
            denominator = sum(value * value for value in delta)
            if denominator <= EPS:
                continue
            t = sum((target[axis] - a[axis]) * delta[axis] for axis in range(2)) / denominator
            if clamp or len(projected_paths) > 1 or i > 0:
                t = max(0.0, t)
            if clamp or i < len(path) - 2:
                t = min(1.0, t)
            factor = a_factor + (b_factor - a_factor) * t
            if clamp:
                factor = max(-1.0, min(1.0, factor))
            projected = (a[0] + t * delta[0], a[1] + t * delta[1])
            distance = sum((target[axis] - projected[axis]) ** 2 for axis in range(2))
            if best is None or distance < best[0]:
                best = (distance, factor)
    return best[1] if best else 0.0
