# SPDX-License-Identifier: GPL-3.0-or-later
"""Control-point merging, independent of Blender's runtime."""

from .geometry import add, sub, mul


def selected_indices(points):
    return [i for i, point in enumerate(points) if point['selected'] and not point['hide']]


def merge_target(points, method, active_index):
    if method == 'ACTIVE':
        if active_index is None or not 0 <= active_index < len(points):
            raise ValueError("Select the destination control point last to make it active")
        return points[active_index].copy()
    target = points[0].copy()
    target['co'] = mul(tuple(sum(p['co'][axis] for p in points) for axis in range(3)),
                       1.0 / len(points))
    for attribute in ('radius', 'tilt', 'weight_softbody', 'co_weight', 'weight'):
        if attribute in target:
            target[attribute] = sum(p[attribute] for p in points) / len(points)
    return target


def merge_points(points, method='CENTER', active_index=None):
    """Collapse selected visible control points in a single spline into one."""
    selected = selected_indices(points)
    if len(selected) < 2:
        raise ValueError("Select at least two control points to merge")
    if method == 'ACTIVE' and active_index not in selected:
        raise ValueError("The active control point must be selected and visible")
    target = merge_target([points[i] for i in selected], method,
                          selected.index(active_index) if method == 'ACTIVE' else None)
    survivor = active_index if method == 'ACTIVE' else selected[0]
    if method == 'CENTER':
        first, last = points[selected[0]], points[selected[-1]]
        target['left'] = add(first['left'], sub(target['co'], first['co']))
        target['right'] = add(last['right'], sub(target['co'], last['co']))
        target['left_type'] = target['right_type'] = 'FREE'
    target['selected'] = True
    target['select_left'] = target['select_right'] = False
    selected_set = set(selected)
    result = [target if i == survivor else p.copy()
              for i, p in enumerate(points) if i == survivor or i not in selected_set]
    return result


def reversed_points(points):
    result = []
    for original in reversed(points):
        point = original.copy()
        point['left'], point['right'] = point['right'], point['left']
        point['left_type'], point['right_type'] = point['right_type'], point['left_type']
        point['select_left'], point['select_right'] = point['select_right'], point['select_left']
        point['tilt'] = -point['tilt']
        result.append(point)
    return result


def join_endpoints(first, first_index, second, second_index, method='CENTER', active_side=None):
    """Join two open splines at their selected endpoints, with one shared point."""
    if first_index not in (0, len(first) - 1) or second_index not in (0, len(second) - 1):
        raise ValueError("Joining separate splines requires selecting their endpoints")
    left = reversed_points(first) if first_index == 0 else [p.copy() for p in first]
    right = reversed_points(second) if second_index == len(second) - 1 else [p.copy() for p in second]
    a, b = left[-1], right[0]
    target = merge_target([a, b], method, active_side)
    target['left'] = add(a['left'], sub(target['co'], a['co']))
    target['right'] = add(b['right'], sub(target['co'], b['co']))
    target['left_type'] = target['right_type'] = 'FREE'
    target['selected'] = True
    target['select_left'] = target['select_right'] = False
    return left[:-1] + [target] + right[1:]
