# SPDX-License-Identifier: GPL-3.0-or-later
"""Blender operators and menu for merging curve points."""

import bpy
from bpy.props import EnumProperty, IntProperty

from .bevel import CURVE_OT_bevel_selected_points
from .common import check_supported, active_point_indices, snapshot_splines, rebuild_splines
from .merge import merge_points, join_endpoints, selected_indices


class CURVE_OT_merge_selected_points(bpy.types.Operator):
    bl_idname = "curve.merge_selected_points"
    bl_label = "Merge Curve Points"
    bl_description = "Merge selected control points at their center or at the active point"
    bl_options = {'REGISTER', 'UNDO'}

    merge_type: EnumProperty(name="Merge", items=(
        ('CENTER', "At Center", "Merge at the average position of selected control points"),
        ('ACTIVE', "At Active", "Merge at the control point selected last"),
    ), default='CENTER')
    active_spline_index: IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})
    active_point_index: IntProperty(default=-1, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return CURVE_OT_bevel_selected_points.poll(context)

    def execute(self, context):
        try:
            check_supported(context)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        objects = list(context.objects_in_mode_unique_data)
        active_object = context.active_object
        active = active_point_indices(context) if self.active_point_index < 0 else None
        if active is not None:
            self.active_spline_index, self.active_point_index = active
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            selections = []
            originals = {}
            for obj in objects:
                if obj.type != 'CURVE':
                    continue
                sources = snapshot_splines(obj.data)
                originals[obj.data] = sources
                for index, (kind, settings, values) in enumerate(sources):
                    selected = selected_indices(values)
                    if selected:
                        if kind not in {'BEZIER', 'POLY'}:
                            raise ValueError("Merge supports Bezier and poly splines")
                        selections.append((obj, index, selected))
            if not selections or sum(len(selected) for _, _, selected in selections) < 2:
                raise ValueError("Select at least two control points to merge")
            obj = selections[0][0]
            if any(other.data != obj.data for other, _, _ in selections):
                raise ValueError("Select points on one curve object to merge")
            sources = originals[obj.data]
            if self.merge_type == 'ACTIVE':
                if obj != active_object or not any(
                        index == self.active_spline_index and self.active_point_index in selected
                        for _, index, selected in selections):
                    raise ValueError("Select the destination control point last to make it active")
            updated = list(sources)
            if len(selections) == 1:
                _, index, selected = selections[0]
                kind, settings, values = sources[index]
                updated[index] = (kind, settings, merge_points(
                    values, self.merge_type,
                    self.active_point_index if self.merge_type == 'ACTIVE' else None))
                removed = len(selected) - 1
            elif len(selections) == 2 and all(len(selected) == 1 for _, _, selected in selections):
                _, first, selection_a = selections[0]
                _, second, selection_b = selections[1]
                kind_a, settings_a, points_a = sources[first]
                kind_b, settings_b, points_b = sources[second]
                if kind_a != kind_b or settings_a['use_cyclic_u'] or settings_b['use_cyclic_u']:
                    raise ValueError("Join endpoints of two open splines of the same type")
                active_side = 0 if self.active_spline_index == first else 1
                values = join_endpoints(points_a, selection_a[0], points_b, selection_b[0],
                                        self.merge_type, active_side)
                settings = settings_b if self.merge_type == 'ACTIVE' and active_side == 1 else settings_a
                updated[first] = (kind_a, settings, values)
                del updated[second]
                removed = 1
            else:
                raise ValueError("Select points in one spline, or one endpoint in each of two open splines")
            try:
                rebuild_splines(obj.data, updated)
            except Exception:
                rebuild_splines(obj.data, sources)
                raise
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        finally:
            bpy.ops.object.mode_set(mode='EDIT')
        self.report({'INFO'}, f"Merged curve points; removed {removed} point(s)")
        return {'FINISHED'}

    def draw(self, context):
        self.layout.prop(self, 'merge_type')


class CURVE_MT_merge_points(bpy.types.Menu):
    bl_idname = "CURVE_MT_merge_points"
    bl_label = "Merge Curve Points"

    def draw(self, context):
        for method, label in (('CENTER', "At Center"), ('ACTIVE', "At Active")):
            self.layout.operator(CURVE_OT_merge_selected_points.bl_idname, text=label).merge_type = method


class CURVE_OT_merge_points_menu(bpy.types.Operator):
    bl_idname = "curve.merge_points_menu"
    bl_label = "Merge Curve Points Menu"
    bl_description = "Choose whether to merge selected points at their center or at the active point"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return CURVE_OT_bevel_selected_points.poll(context)

    def execute(self, context):
        bpy.ops.wm.call_menu(name=CURVE_MT_merge_points.bl_idname)
        return {'FINISHED'}
