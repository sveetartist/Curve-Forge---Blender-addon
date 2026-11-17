# SPDX-License-Identifier: GPL-3.0-or-later
"""Curve-only G / G-G movement with a modal slide along the original path."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty
from bpy_extras import view3d_utils
from mathutils import Vector

from .common import active_point_indices, snapshot, write_points
from .slide_geometry import prepare_slide, move_points, nearest_factor, position_on_path, slide_points
from .interaction import ModalFeedback, close_feedback, edit_numeric, numeric_value


def move_properties(mode):
    return {
        'operation_mode': EnumProperty(name="Mode", items=(
            ('GRAB', "Move", "Move selected curve points freely"),
            ('SLIDE', "Slide", "Slide selected points along their original neighboring segments")), default=mode),
        'factor': FloatProperty(name="Factor", description="Fraction of the neighboring segment; negative slides towards the previous point", default=0.0),
        'offset': FloatVectorProperty(name="Offset", description="Movement in world coordinates", subtype='TRANSLATION', default=(0.0, 0.0, 0.0)),
        'use_clamp': BoolProperty(name="Clamp", description="Stop at neighboring control points", default=True),
    }


class CurvePointMove:
    def _native_move(self):
        bpy.ops.transform.translate('INVOKE_DEFAULT')
        return {'CANCELLED'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'CURVE' and context.mode == 'EDIT_CURVE'

    def _prepare(self, context):
        self._sources = []
        for obj in context.objects_in_mode_unique_data:
            if obj.type != 'CURVE':
                continue
            for index, spline in enumerate(obj.data.splines):
                original = snapshot(spline)
                if not any(not point['hide'] and (point['selected'] or point['select_left'] or point['select_right']) for point in original):
                    continue
                if obj.data.shape_keys is not None:
                    raise ValueError("Curve point slide does not support shape keys")
                if spline.type not in {'BEZIER', 'POLY'}:
                    raise ValueError("Curve point slide supports Bezier and poly splines")
                representative = context.active_object if context.active_object.data == obj.data else obj
                paths = prepare_slide(original, spline.use_cyclic_u, spline.type == 'BEZIER')
                self._sources.append((representative, index, original, paths))
        if not self._sources:
            raise ValueError("Select curve control points to move or slide")

    def _apply(self):
        for obj, index, original, paths in self._sources:
            if self.operation_mode == 'SLIDE':
                values = slide_points(original, paths, self.factor, self.use_clamp and not self._alt)
            else:
                delta = obj.matrix_world.to_3x3().inverted_safe() @ Vector(self.offset)
                values = move_points(original, tuple(delta))
            write_points(obj.data.splines[index], values)
            obj.data.update_tag()

    def _restore(self):
        for obj, index, original, _ in self._sources:
            write_points(obj.data.splines[index], original)
            obj.data.update_tag()

    def execute(self, context):
        try:
            self._prepare(context)
        except ValueError as exc:
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        if self.operation_mode == 'SLIDE' and not any(paths for _, _, _, paths in self._sources):
            self.report({'WARNING'}, "Select a control point with a visible, nonzero neighboring segment")
            return {'CANCELLED'}
        self._alt = False
        try:
            self._apply()
        except Exception as exc:
            self._restore()
            self.report({'ERROR'}, f"Curve point move failed: {exc}")
            return {'CANCELLED'}
        return {'FINISHED'}

    def _reference(self, context):
        active = active_point_indices(context)
        eligible = [(obj, index, points, paths, i) for obj, index, points, paths in self._sources for i in paths]
        if not eligible:
            # Free grab is still available for handle-only selections.
            return None
        return next((entry for entry in eligible if entry[0] == context.active_object and active == (entry[1], entry[4])), eligible[0])

    def _project_paths(self):
        obj, _, points, paths, index = self._ref
        self._projected_paths = []
        for side, path in ((-1, paths[index][0]), (1, paths[index][1])):
            if path is None:
                continue
            samples = []
            for step in range(33):
                factor = side * step / 32.0
                co = position_on_path(points[index], paths[index], factor)
                screen = view3d_utils.location_3d_to_region_2d(self._region, self._view, obj.matrix_world @ Vector(co))
                if screen is not None:
                    samples.append((factor, tuple(screen)))
            extended = position_on_path(points[index], paths[index], side * 2.0, False)
            screen = view3d_utils.location_3d_to_region_2d(self._region, self._view, obj.matrix_world @ Vector(extended))
            if screen is not None:
                samples.append((side * 2.0, tuple(screen)))
            self._projected_paths.append(samples)

    def invoke(self, context, event):
        self._feedback = None
        self._closed = False
        try:
            return self._invoke(context, event)
        except Exception as exc:
            self.cancel(context)
            self.report({'ERROR'}, f"Curve point preview failed: {exc}")
            return {'CANCELLED'}

    def _invoke(self, context, event):
        # Blender remembers registered operator properties after confirmation.
        # A fresh G must start in Grab even if the previous invocation slid.
        self.operation_mode = self._initial_mode
        if context.area is None or context.area.type != 'VIEW_3D':
            return self.execute(context)
        if self.operation_mode == 'GRAB' and context.scene.tool_settings.use_proportional_edit:
            return self._native_move()
        try:
            self._prepare(context)
        except ValueError as exc:
            if self.operation_mode == 'GRAB':
                return self._native_move()
            self.report({'WARNING'}, str(exc))
            return {'CANCELLED'}
        self._ref = self._reference(context)
        if self._ref is None:
            if self.operation_mode == 'GRAB':
                return self._native_move()
            self.report({'WARNING'}, "Select a control point with a visible, nonzero neighboring segment")
            return {'CANCELLED'}
        self._area, self._workspace, self._window = context.area, context.workspace, context.window
        self._region = next(region for region in context.area.regions if region.type == 'WINDOW')
        self._view = context.area.spaces.active.region_3d
        obj, _, points, _, index = self._ref
        self._center = obj.matrix_world @ Vector(points[index]['co'])
        self._anchor = view3d_utils.location_3d_to_region_2d(self._region, self._view, self._center)
        if self._anchor is None:
            self.report({'WARNING'}, "The selected point is behind the viewport camera")
            return {'CANCELLED'}
        self._origin = Vector((event.mouse_x - self._region.x, event.mouse_y - self._region.y))
        self._last_mouse = self._origin.copy()
        self._virtual_mouse = Vector((0.0, 0.0))
        self._numeric = ''
        self._slide_bias = 0.0
        self._grab_base = Vector()
        self._axis = None
        self._local_axis = self._plane = self._alt = False
        self._closed = False
        self._trigger_key = event.type if event.type not in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER', 'SPACE'} else 'G'
        self.factor, self.offset = 0.0, (0.0, 0.0, 0.0)
        self._project_paths()
        self._feedback = ModalFeedback(context)
        self._feedback.on_cancel = self.cancel
        self._update_header()
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _axis_vector(self, axis):
        if self._local_axis:
            return self._ref[0].matrix_world.to_3x3().col[axis].normalized()
        return Vector(tuple(1.0 if i == axis else 0.0 for i in range(3)))

    def _numeric_value(self):
        return numeric_value(self._numeric)

    def _update_amount(self, event):
        if self.operation_mode == 'SLIDE':
            if self._numeric:
                self.factor = self._numeric_value()
            else:
                target = self._anchor + self._virtual_mouse
                clamp = self.use_clamp and not self._alt
                factor = nearest_factor(self._projected_paths, tuple(target), clamp and self._slide_bias == 0) + self._slide_bias
                if self.use_clamp and not self._alt:
                    factor = max(-1.0, min(1.0, factor))
                self.factor = round(factor * 10.0) / 10.0 if event.ctrl else factor
        else:
            if self._numeric:
                axes = [self._axis] if self._axis is not None and not self._plane else [i for i in range(3) if i != self._axis]
                delta = sum((self._axis_vector(i) for i in axes), Vector()) * self._numeric_value()
            else:
                a = view3d_utils.region_2d_to_location_3d(self._region, self._view, self._origin, self._center)
                b = view3d_utils.region_2d_to_location_3d(self._region, self._view, self._origin + self._virtual_mouse, self._center)
                delta = b - a + self._grab_base
                if self._axis is not None:
                    direction = self._axis_vector(self._axis)
                    component = direction * delta.dot(direction)
                    delta = delta - component if self._plane else component
                if event.ctrl:
                    increment = 0.1 if event.shift else 1.0
                    if self._axis is not None and not self._plane:
                        direction = self._axis_vector(self._axis)
                        delta = direction * (round(delta.dot(direction) / increment) * increment)
                    else:
                        delta = Vector(tuple(round(value / increment) * increment for value in delta))
                        if self._axis is not None:
                            direction = self._axis_vector(self._axis)
                            delta -= direction * delta.dot(direction)
            self.offset = delta
        self._apply()
        self._update_header()

    def _update_header(self):
        if self.operation_mode == 'SLIDE':
            value = self._numeric or f'{self.factor:.4f}'
            label = f"Curve Point Slide | Factor: {value} | Clamp: {'On' if self.use_clamp and not self._alt else 'Off'}"
            controls = "C: clamp | Alt: unclamp | Ctrl: increments | Shift: precision"
        else:
            label = "Curve Point Move | Offset: " + ', '.join(f'{v:.4g}' for v in self.offset)
            if self._axis is not None:
                label += f" | {'Local' if self._local_axis else 'Global'} {'Plane' if self._plane else 'Axis'}: {'XYZ'[self._axis]}"
            controls = f"{self._trigger_key} again: slide | X/Y/Z: axis | Shift+axis: plane | Shift: precision | Ctrl: increments"
        self._area.header_text_set(label)
        self._workspace.status_text_set(controls + " | Type: amount | Enter/LMB: confirm | Esc/RMB: cancel")
        self._area.tag_redraw()

    def _cleanup(self):
        close_feedback(self)
        self._closed = True

    def cancel(self, context):
        if not self._closed:
            try:
                if hasattr(self, '_sources'):
                    self._restore()
            finally:
                self._cleanup()

    def modal(self, context, event):
        if self._closed:
            return {'CANCELLED'}
        try:
            return self._modal(context, event)
        except Exception as exc:
            self.cancel(context)
            self.report({'ERROR'}, f"Curve point preview failed: {exc}")
            return {'CANCELLED'}

    def _modal(self, context, event):
        self._alt = event.alt
        if event.type in {'LEFT_ALT', 'RIGHT_ALT'}:
            self._update_amount(event)
            return {'RUNNING_MODAL'}
        if event.value == 'PRESS':
            if event.type in {'ESC', 'RIGHTMOUSE'}:
                self.cancel(context)
                return {'CANCELLED'}
            if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER', 'SPACE'}:
                self._cleanup()
                return {'FINISHED'}
            if event.type in {'G', self._trigger_key} and not getattr(event, 'is_repeat', False):
                if self.operation_mode == 'GRAB':
                    self.operation_mode = 'SLIDE'
                    self._numeric = ''
                    self._virtual_mouse = Vector((0.0, 0.0))
                    self._slide_bias = 0.0
                    self.factor = 0.0
                    self._apply()
                    self._update_header()
                return {'RUNNING_MODAL'}
            if event.type in {'R', 'S'} and self.operation_mode == 'GRAB' and not self._numeric:
                self.cancel(context)
                operator = bpy.ops.transform.rotate if event.type == 'R' else bpy.ops.transform.resize
                operator('INVOKE_DEFAULT')
                return {'CANCELLED'}
            if event.type in {'X', 'Y', 'Z'} and self.operation_mode == 'GRAB':
                axis = 'XYZ'.index(event.type)
                if self._axis != axis or self._plane != event.shift:
                    self._axis, self._local_axis = axis, False
                elif not self._local_axis:
                    self._local_axis = True
                else:
                    self._axis = None
                    self._local_axis = False
                self._plane = event.shift
            elif event.type == 'C' and self.operation_mode == 'SLIDE':
                self.use_clamp = not self.use_clamp
            else:
                edited = edit_numeric(self._numeric, event, signed=True)
                if edited is None:
                    return {'RUNNING_MODAL'}
                if self._numeric and not edited:
                    self._slide_bias = self.factor
                    self._grab_base = Vector(self.offset)
                    self._virtual_mouse = Vector((0.0, 0.0))
                self._numeric = edited
        elif event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            mouse = Vector((event.mouse_x - self._region.x, event.mouse_y - self._region.y))
            if not self._numeric:
                self._virtual_mouse += (mouse - self._last_mouse) * (0.1 if event.shift else 1.0)
            self._last_mouse = mouse
        elif event.type not in {'LEFT_ALT', 'RIGHT_ALT'}:
            return {'RUNNING_MODAL'}
        self._update_amount(event)
        return {'RUNNING_MODAL'}

    def draw(self, context):
        self.layout.prop(self, 'operation_mode')
        if self.operation_mode == 'SLIDE':
            self.layout.prop(self, 'factor')
            self.layout.prop(self, 'use_clamp')
        else:
            self.layout.prop(self, 'offset')


class CURVE_OT_grab_or_slide(CurvePointMove, bpy.types.Operator):
    bl_idname = 'curve.grab_or_slide'
    bl_label = 'Move / Slide Curve Points'
    bl_description = 'Move selected curve points; repeat the move key to slide along the curve'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    _initial_mode = 'GRAB'
    __annotations__ = move_properties('GRAB')


class CURVE_OT_slide_points(CurvePointMove, bpy.types.Operator):
    bl_idname = 'curve.slide_points'
    bl_label = 'Slide Curve Points'
    bl_description = 'Slide selected control points along their original neighboring curve segments'
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}
    _initial_mode = 'SLIDE'
    __annotations__ = move_properties('SLIDE')
