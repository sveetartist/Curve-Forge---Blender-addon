# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared curve data and selection helpers."""

import bpy

def snapshot(spline):
    bezier = spline.type == 'BEZIER'
    result = []
    for point in spline.bezier_points if bezier else spline.points:
        result.append({
            "co": tuple(point.co[:3]),
            "left": tuple(point.handle_left) if bezier else tuple(point.co[:3]),
            "right": tuple(point.handle_right) if bezier else tuple(point.co[:3]),
            "left_type": point.handle_left_type if bezier else 'FREE',
            "right_type": point.handle_right_type if bezier else 'FREE',
            "selected": point.select_control_point if bezier else point.select,
            "select_left": point.select_left_handle if bezier else False,
            "select_right": point.select_right_handle if bezier else False,
            "hide": point.hide,
            "radius": point.radius,
            "tilt": point.tilt,
            "weight_softbody": point.weight_softbody,
            "co_weight": 1.0 if bezier else point.co[3],
            "weight": 1.0 if bezier else point.weight,
        })
    return result


def write_points(spline, values):
    bezier = spline.type == 'BEZIER'
    collection = spline.bezier_points if bezier else spline.points
    collection.add(len(values) - len(collection))
    if bezier:
        for point in collection:
            point.handle_left_type = point.handle_right_type = 'FREE'
    for point, value in zip(collection, values):
        if bezier:
            point.co = value["co"]
            point.handle_left = value["left"]
            point.handle_right = value["right"]
            point.select_control_point = value["selected"]
            point.select_left_handle = value["select_left"]
            point.select_right_handle = value["select_right"]
        else:
            point.co = (*value["co"], value["co_weight"])
            point.select = value["selected"]
            point.weight = value.get("weight", 1.0)
        point.hide = value["hide"]
        point.radius = value["radius"]
        point.tilt = value["tilt"]
        # Blender's default can be below this property's assignment minimum.
        if point.weight_softbody != value["weight_softbody"]:
            point.weight_softbody = value["weight_softbody"]
    if bezier:
        for point, value in zip(collection, values):
            point.handle_left_type = value["left_type"]
            point.handle_right_type = value["right_type"]


def check_supported(context):
    objects = [obj for obj in context.objects_in_mode_unique_data if obj.type == 'CURVE']
    if any(obj.data.shape_keys is not None for obj in objects):
        raise ValueError("Curves with shape keys are not supported")
    if any(obj.data.animation_data is not None for obj in objects):
        raise ValueError("Remove curve-data animation/drivers before changing point topology")
    if any(mod.type == 'HOOK' for obj in objects for mod in obj.modifiers):
        raise ValueError("Apply or remove Hook modifiers before changing point topology")


def active_point_position(context):
    """Read Blender's native active edit point without changing the 3D cursor."""
    window = context.window
    if window is None:
        return None
    area = context.area if context.area and context.area.type == 'VIEW_3D' else next(
        (area for area in window.screen.areas if area.type == 'VIEW_3D'), None)
    if area is None:
        return None
    region = next((region for region in area.regions if region.type == 'WINDOW'), None)
    if region is None:
        return None
    cursor = context.scene.cursor
    location = cursor.location.copy()
    try:
        with context.temp_override(window=window, area=area, region=region):
            if bpy.ops.view3d.snap_cursor_to_active('EXEC_DEFAULT', False) == {'FINISHED'}:
                return cursor.location.copy()
    finally:
        cursor.location = location
    return None


def active_point_indices(context):
    """Resolve native active identity even when several points share a position.

    Checker Deselect uses Blender's active point as its origin. A period longer
    than the spline isolates that point; restore every selection flag afterwards.
    """
    if active_point_position(context) is None:
        return None
    curve = context.active_object.data
    spline = curve.splines.active
    if spline is None:
        return None
    spline_index = list(curve.splines).index(spline)
    collection = spline.bezier_points if spline.type == 'BEZIER' else spline.points
    saved = []
    for obj in context.objects_in_mode_unique_data:
        if obj.type != 'CURVE':
            continue
        for other in obj.data.splines:
            names = ('select_control_point', 'select_left_handle', 'select_right_handle') if other.type == 'BEZIER' else ('select',)
            points = other.bezier_points if other.type == 'BEZIER' else other.points
            saved.extend((point, names, tuple(getattr(point, name) for name in names)) for point in points)
    try:
        if bpy.ops.curve.select_nth('EXEC_DEFAULT', False,
                                    nth=1, skip=len(collection) + 1, offset=-1) != {'FINISHED'}:
            return None
        indices = [i for i, point in enumerate(collection) if not point.hide and (
            point.select_control_point if spline.type == 'BEZIER' else point.select)]
        return (spline_index, indices[0]) if len(indices) == 1 else None
    finally:
        for point, names, values in saved:
            for name, value in zip(names, values):
                setattr(point, name, value)


def snapshot_splines(curve):
    return [(spline.type,
             {prop.identifier: getattr(spline, prop.identifier)
              for prop in spline.bl_rna.properties
              if not prop.is_readonly and prop.identifier != 'type'},
             snapshot(spline)) for spline in curve.splines]


def rebuild_splines(curve, sources):
    """Rebuild shrinking point collections while retaining the curve datablock."""
    curve.splines.clear()
    for kind, settings, values in sources:
        spline = curve.splines.new(kind)
        write_points(spline, values)
        for name, value in settings.items():
            # Some untouched defaults (e.g. order_v on a 1D spline) lie outside
            # RNA's setter bounds. Keep matching defaults instead of clamping.
            if getattr(spline, name) != value:
                setattr(spline, name, value)
    curve.update_tag()
