# SPDX-License-Identifier: GPL-3.0-or-later
"""Interactive curve-corner beveling."""

import bpy
from math import hypot, sqrt
from bpy.props import EnumProperty, FloatProperty, IntProperty
from bpy_extras import view3d_utils
from mathutils import Vector

from .geometry import bevel_points, prepare_edges
from .common import snapshot, write_points, check_supported
from .interaction import ModalFeedback, PreviewSchedule, close_feedback, edit_numeric, numeric_value


class BevelSession:
    """Keep originals intact during preview; write topology only on confirm.

    Temporary curve datablocks allow segment counts to decrease without RNA
    point deletion, which Blender does not expose. Linked users keep the same
    original datablock, and cancel simply restores it rather than using undo.
    """

    def __init__(self, context):
        self.objects = [(obj, obj.data) for obj in context.objects_in_mode
                        if obj.type == 'CURVE']
        self.sources = {}
        self.previews = {}
        self.plans = {}
        self.changed = self.clamped = 0
        self.closed = False
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            for obj, curve in self.objects:
                if curve in self.sources:
                    continue
                self.sources[curve] = []
                for index, spline in enumerate(curve.splines):
                    if spline.type in {'BEZIER', 'POLY'}:
                        values = snapshot(spline)
                        self.sources[curve].append((index, values, spline.use_cyclic_u,
                                                   spline.type == 'BEZIER',
                                                   prepare_edges(values, spline.use_cyclic_u,
                                                                 spline.type == 'BEZIER')))
        finally:
            bpy.ops.object.mode_set(mode='EDIT')

    def calculate(self, width, segments, shape, amount_type):
        self.plans = {}
        self.changed = self.clamped = 0
        for curve, sources in self.sources.items():
            plans = {}
            for index, original, cyclic, bezier, prepared in sources:
                values, count, limited = bevel_points(
                    original, cyclic, width, segments, shape == 'ROUND', bezier,
                    amount_type=amount_type, prepared=prepared,
                )
                if values is not None:
                    plans[index] = values
                    self.changed += count
                    self.clamped += limited
            self.plans[curve] = plans

    def _assign(self, original, replacement):
        for obj, curve in self.objects:
            if curve == original:
                obj.data = replacement

    def _remove_preview(self, original):
        preview = self.previews.pop(original, None)
        if preview is not None:
            self._assign(original, original)
            bpy.data.curves.remove(preview)

    def preview(self, width, segments, shape, amount_type):
        self.calculate(width, segments, shape, amount_type)
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            for original, sources in self.sources.items():
                plans = self.plans[original]
                if not plans:
                    self._remove_preview(original)
                    continue
                preview = self.previews.get(original)
                if preview is not None:
                    # Recreate from the original when shrinking any spline.
                    for index, baseline, _, bezier, _ in sources:
                        collection = preview.splines[index].bezier_points if bezier else preview.splines[index].points
                        if len(collection) > len(plans.get(index, baseline)):
                            self._remove_preview(original)
                            preview = None
                            break
                if preview is None:
                    preview = original.copy()
                    self.previews[original] = preview
                    self._assign(original, preview)
                for index, values in plans.items():
                    write_points(preview.splines[index], values)
                preview.update_tag()
        finally:
            bpy.ops.object.mode_set(mode='EDIT')

    def finish(self, commit=False):
        if self.closed:
            return
        bpy.ops.object.mode_set(mode='OBJECT')
        try:
            for original in list(self.previews):
                self._remove_preview(original)
            if commit:
                for original, plans in self.plans.items():
                    for index, values in plans.items():
                        write_points(original.splines[index], values)
                    original.update_tag()
        finally:
            self.closed = True
            bpy.ops.object.mode_set(mode='EDIT')

    def center(self):
        positions = []
        for obj, curve in self.objects:
            for _, original, _, _, _ in self.sources[curve]:
                positions.extend(obj.matrix_world @ Vector(p["co"]) for p in original
                                 if p["selected"] and not p["hide"])
        return sum(positions, Vector()) / len(positions) if positions else Vector()


class CURVE_OT_bevel_selected_points(bpy.types.Operator):
    bl_idname = "curve.bevel_selected_points"
    bl_label = "Bevel Curve Points"
    bl_description = "Bevel selected curve corners: mouse sets radius, wheel changes segments"
    bl_options = {'REGISTER', 'UNDO', 'BLOCKING'}

    width: FloatProperty(
        name="Amount", description="Bevel radius or offset in local curve units",
        default=0.1, min=0.0, subtype='DISTANCE',
    )
    segments: IntProperty(
        name="Segments", description="Number of segments in each new bevel",
        default=4, min=1, max=32,
    )
    shape: EnumProperty(
        name="Shape", items=(
            ('ROUND', "Round", "Smooth tangent fillet; circular approximation on straight corners"),
            ('CHAMFER', "Chamfer", "Straight cut across each corner"),
        ), default='ROUND',
    )
    amount_type: EnumProperty(
        name="Amount Type", items=(
            ('RADIUS', "Radius", "Radius of the rounded corner; approximate for curved segments"),
            ('OFFSET', "Offset", "Distance to trim along each side of the original curve"),
        ), default='RADIUS',
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and obj.type == 'CURVE' and context.mode == 'EDIT_CURVE'

    def _new_session(self, context):
        try:
            check_supported(context)
        except ValueError as exc:
            self.report({'ERROR'}, str(exc))
            return None
        return BevelSession(context)

    def _report_result(self, session):
        if not session.changed:
            self.report({'WARNING'}, "Select corner control points on a Bezier or poly spline; endpoints and smooth points are skipped")
            return {'CANCELLED'}
        message = f"Beveled {session.changed} curve corner(s)"
        self.report({'INFO'}, message)
        return {'FINISHED'}

    def execute(self, context):
        session = self._new_session(context)
        if session is None:
            return {'CANCELLED'}
        try:
            session.calculate(self.width, self.segments, self.shape, self.amount_type)
        except Exception as exc:
            session.finish()
            self.report({'ERROR'}, f"Bevel failed: {exc}")
            return {'CANCELLED'}
        session.finish(commit=bool(session.changed))
        return self._report_result(session)

    def invoke(self, context, event):
        self._closed = False
        self._feedback = None
        try:
            return self._invoke(context, event)
        except Exception as exc:
            self.cancel(context)
            self.report({'ERROR'}, f"Bevel preview failed: {exc}")
            return {'CANCELLED'}

    def _invoke(self, context, event):
        if context.area is None or context.area.type != 'VIEW_3D':
            return self.execute(context)
        self._session = self._new_session(context)
        if self._session is None:
            return {'CANCELLED'}
        # Test eligibility without modifying geometry before entering modal mode.
        self._session.calculate(0.0001, 1, self.shape, self.amount_type)
        if not self._session.changed:
            self._session.finish()
            return self._report_result(self._session)
        self._area = context.area
        self._workspace = context.workspace
        self._window = context.window
        self._mouse_origin = (event.mouse_x, event.mouse_y)
        self._last_distance = 0.0
        self._numeric = ""
        self._drag_amount = 0.0
        self._schedule = PreviewSchedule()
        self.width = 0.0
        self._session.calculate(0.0, self.segments, self.shape, self.amount_type)
        region = next(r for r in context.area.regions if r.type == 'WINDOW')
        view = context.area.spaces.active.region_3d
        center = self._session.center()
        # Convert pixels at the selected points' depth into local curve units.
        location = (region.width / 2.0, region.height / 2.0)
        a = view3d_utils.region_2d_to_location_3d(region, view, location, center)
        b = view3d_utils.region_2d_to_location_3d(region, view, (location[0] + 1, location[1]), center)
        scale = context.active_object.matrix_world.to_scale().length / sqrt(3.0)
        self._units_per_pixel = max(1.0e-8, (b - a).length / max(scale, 1.0e-8))
        self._feedback = ModalFeedback(context, timer=True)
        self._feedback.on_cancel = self.cancel
        self._update_header()
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _update_header(self):
        value = self._numeric if self._numeric else f"{self.width:.5g}"
        label = "Radius" if self.amount_type == 'RADIUS' else "Offset"
        self._area.header_text_set(
            f"Bevel Curve Points | {label}: {value} (local units) | Segments: {self.segments} | {self.shape.title()}")
        self._workspace.status_text_set("Drag: amount | Wheel: segments | Shift: precision | Type: local units | M: shape | R: radius/offset | Enter: confirm | Esc: cancel")
        self._area.tag_redraw()

    def _cleanup(self):
        close_feedback(self)
        self._closed = True

    def cancel(self, context):
        try:
            if hasattr(self, '_session'):
                self._session.finish()
        finally:
            self._cleanup()

    def modal(self, context, event):
        if self._closed:
            return {'CANCELLED'}
        try:
            return self._modal(context, event)
        except Exception as exc:
            self.cancel(context)
            self.report({'ERROR'}, f"Bevel preview failed: {exc}")
            return {'CANCELLED'}

    def _preview(self, force=False):
        self._schedule.apply((self.width, self.segments, self.shape, self.amount_type),
                             self._session.preview, force=force)

    def _modal(self, context, event):
        if event.type == 'TIMER':
            # Blender's Event RNA does not expose which timer generated it.
            # The schedule enforces our update rate even with other timers active.
            self._preview()
            return {'RUNNING_MODAL'}
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self.cancel(context)
            return {'CANCELLED'}
        if event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER', 'SPACE'} and event.value == 'PRESS':
            self._preview(force=True)
            self._session.finish(commit=bool(self._session.changed))
            self._cleanup()
            return {'FINISHED'} if self._session.changed else {'CANCELLED'}

        changed = False
        if event.type in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}:
            distance = hypot(event.mouse_x - self._mouse_origin[0], event.mouse_y - self._mouse_origin[1])
            if not self._numeric:
                sensitivity = 0.1 if event.shift else 1.0
                self._drag_amount = max(0.0, self._drag_amount + (distance - self._last_distance)
                                        * self._units_per_pixel * sensitivity)
                self.width = self._drag_amount
                changed = True
            self._last_distance = distance
        elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} and event.value == 'PRESS':
            self.segments = max(1, min(32, self.segments + (1 if event.type == 'WHEELUPMOUSE' else -1)))
            changed = True
        elif event.value == 'PRESS':
            edited = edit_numeric(self._numeric, event)
            if edited is not None:
                if self._numeric and not edited:
                    self._drag_amount = self.width
                self._numeric = edited
                self.width = numeric_value(edited) if edited else self._drag_amount
                changed = True
            elif event.type == 'M':
                self.shape = 'CHAMFER' if self.shape == 'ROUND' else 'ROUND'
                changed = True
            elif event.type == 'R':
                self.amount_type = 'OFFSET' if self.amount_type == 'RADIUS' else 'RADIUS'
                changed = True
        if changed:
            self._preview()
            self._update_header()
        return {'RUNNING_MODAL'}

    def draw(self, context):
        self.layout.prop(self, "amount_type")
        self.layout.prop(self, "width", text="Radius" if self.amount_type == 'RADIUS' else "Offset")
        self.layout.prop(self, "segments")
        self.layout.prop(self, "shape")
